"""The JSON/SSE API the React app talks to. Business logic lives in the other compass modules;
this file only does HTTP: auth, validation, status codes and streaming."""

import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from compass.config import Settings
from compass.consent import CONSENT_VERSION, needs_consent
from compass.documents import (
    MAX_DOCUMENTS,
    MAX_UPLOAD_BYTES,
    DocumentError,
    budget_report,
    extract_text,
    select_for_prompt,
)
from compass.jwt_auth import AuthError, AuthUser, JWTVerifier
from compass.llm import (
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    stream_reply,
    to_api_messages,
)
from compass.memory import SUMMARIES_IN_PROMPT, catch_up, end_conversation
from compass.prompts import build_system_prompt

log = logging.getLogger("compass")
MAX_MESSAGE_CHARS = 8000


class ConsentIn(BaseModel):
    agree: bool
    training_opt_in: bool = False


class TrainingIn(BaseModel):
    opted_in: bool


class ProfileIn(BaseModel):
    role: str = Field("", max_length=200)
    industry: str = Field("", max_length=200)
    goals: str = Field("", max_length=3000)
    cv_text: str = Field("", max_length=20000)


class DocumentPatch(BaseModel):
    enabled: bool


class ChatIn(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_CHARS)
    conversation_id: str | None = None


class FeedbackIn(BaseModel):
    value: Literal[1, -1] | None


class DeleteIn(BaseModel):
    confirm: Literal["DELETE"]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _public_documents(documents: list[dict]) -> list[dict]:
    keep = ("id", "name", "char_count", "truncated", "enabled", "created_at")
    return [{k: d[k] for k in keep} for d in documents]


def create_app(settings: Settings, *, verifier=None, store_factory=None, llm=None, static_dir=None) -> FastAPI:
    """`verifier`, `store_factory` and `llm` can be replaced in tests; the defaults are the real ones."""
    if verifier is None:
        verifier = JWTVerifier(settings.jwks_endpoint, settings.jwt_issuer)
    if llm is None:
        from compass.llm import OpenRouterClient

        llm = OpenRouterClient(settings.openrouter_api_key, settings.site_url)
    if store_factory is None:
        from supabase import ClientOptions, create_client

        from compass.db import Store

        def store_factory(user: AuthUser):
            # Act as the user: their JWT in the Authorization header makes Row Level Security apply.
            options = ClientOptions(headers={"Authorization": f"Bearer {user.token}"}, auto_refresh_token=False, persist_session=False)
            return Store(create_client(settings.supabase_url, settings.supabase_key, options), user.id)

    app = FastAPI(title="Compass API", docs_url=None, redoc_url=None, openapi_url=None)
    catching_up: set[str] = set()  # users whose earlier sessions are being summarised right now

    # auth ----------------------------------------------------------------------------
    def current_user(request: Request) -> AuthUser:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Please sign in.")
        try:
            return verifier.verify(token)
        except AuthError as exc:
            raise HTTPException(401, str(exc)) from exc

    def store_for(user: AuthUser = Depends(current_user)):
        return store_factory(user)

    def consented_store(store=Depends(store_for)):
        if needs_consent(store.get_consent()):
            raise HTTPException(403, "Please accept the privacy notice first.")
        return store

    # security headers ---------------------------------------------------------------------
    csp = "; ".join([
        "default-src 'self'",
        f"connect-src 'self' {settings.supabase_url.rstrip('/')}",  # the browser signs in with Supabase directly
        "img-src 'self' data:",
        "style-src 'self' 'unsafe-inline'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")  # never cache anyone's data
        return response

    # errors ------------------------------------------------------------------------------
    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse({"detail": "That request wasn't valid. Please check it and try again."}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("Unhandled error")  # never log message content, only the traceback
        return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)

    # public ------------------------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/config")
    def config():
        # The publishable key is designed to be public; Row Level Security protects the data.
        return {"supabase_url": settings.supabase_url, "supabase_publishable_key": settings.supabase_key}

    # bootstrap / consent ---------------------------------------------------------------------------
    @app.get("/api/bootstrap")
    def bootstrap(background: BackgroundTasks, user: AuthUser = Depends(current_user), store=Depends(store_for)):
        consent = store.get_consent()
        accepted = not needs_consent(consent)
        payload = {
            "user": {"id": user.id, "email": user.email},
            "consent": {
                "accepted": accepted,
                "current_version": CONSENT_VERSION,
                "training_opt_in": bool(consent.get("training_opt_in")) if accepted else False,
            },
        }
        if not accepted:  # nothing else is loaded until the user has agreed
            return payload
        documents = store.list_documents()
        payload.update(
            profile=_profile_out(store.get_profile()),
            documents={"items": _public_documents(documents), "budget": budget_report(documents)},
            conversations=store.list_conversations(),
        )
        if user.id not in catching_up:  # summarise sessions that ended when the tab was closed
            catching_up.add(user.id)

            def run():
                try:
                    catch_up(store, llm, settings.model)
                except Exception:
                    log.exception("Catch-up summaries failed")
                finally:
                    catching_up.discard(user.id)

            background.add_task(run)
        return payload

    @app.post("/api/consent")
    def accept_consent(body: ConsentIn, store=Depends(store_for)):
        if not body.agree:
            raise HTTPException(422, "You need to agree to continue.")
        store.save_consent(CONSENT_VERSION, body.training_opt_in)
        return {"ok": True}

    @app.put("/api/consent/training")
    def set_training(body: TrainingIn, store=Depends(consented_store)):
        store.set_training_opt_in(body.opted_in)
        return {"training_opt_in": body.opted_in}

    @app.delete("/api/me/data")
    def delete_data(body: DeleteIn, store=Depends(store_for)):
        store.delete_my_data()
        return {"ok": True}

    # profile ---------------------------------------------------------------------------------------
    def _profile_out(profile: dict) -> dict:
        return {k: profile.get(k, "") or "" for k in ("role", "industry", "goals", "cv_text")}

    @app.get("/api/profile")
    def get_profile(store=Depends(consented_store)):
        return _profile_out(store.get_profile())

    @app.put("/api/profile")
    def put_profile(body: ProfileIn, store=Depends(consented_store)):
        store.save_profile(**body.model_dump())
        return _profile_out(store.get_profile())

    # documents ---------------------------------------------------------------------------------------
    def _documents_out(store) -> dict:
        documents = store.list_documents()
        return {"items": _public_documents(documents), "budget": budget_report(documents)}

    @app.get("/api/documents")
    def list_documents(store=Depends(consented_store)):
        return _documents_out(store)

    @app.post("/api/documents")
    def upload_documents(files: list[UploadFile] = File(...), store=Depends(consented_store)):
        existing = len(store.list_documents())
        results = []
        for upload in files:
            name = (upload.filename or "document").strip()[:200]
            if existing >= MAX_DOCUMENTS:
                results.append({"name": name, "ok": False, "error": f"You can keep up to {MAX_DOCUMENTS} documents. Remove one to add more."})
                continue
            data = upload.file.read(MAX_UPLOAD_BYTES + 1)  # never hold more than the limit in memory
            try:
                doc = extract_text(name, data)
                store.add_document(doc.name, doc.text, doc.truncated)
            except DocumentError as exc:
                results.append({"name": name, "ok": False, "error": str(exc)})
            else:
                existing += 1
                results.append({"name": name, "ok": True, "truncated": doc.truncated})
        return {"results": results, **_documents_out(store)}

    @app.patch("/api/documents/{document_id}")
    def patch_document(document_id: str, body: DocumentPatch, store=Depends(consented_store)):
        store.set_document_enabled(document_id, body.enabled)
        return _documents_out(store)

    @app.delete("/api/documents/{document_id}")
    def remove_document(document_id: str, store=Depends(consented_store)):
        store.delete_document(document_id)
        return _documents_out(store)

    # conversations -----------------------------------------------------------------------------------
    @app.get("/api/conversations")
    def conversations(store=Depends(consented_store)):
        return {"items": store.list_conversations()}

    @app.get("/api/conversations/{conversation_id}")
    def conversation(conversation_id: str, store=Depends(consented_store)):
        if store.get_conversation(conversation_id) is None:
            raise HTTPException(404, "That conversation wasn't found.")
        return {
            "id": conversation_id,
            "messages": [
                {"id": m["id"], "role": m["role"], "content": m["content"], "feedback": m.get("feedback")}
                for m in store.get_messages(conversation_id)
            ],
        }

    @app.post("/api/conversations/{conversation_id}/end")
    def end(conversation_id: str, store=Depends(consented_store)):
        if store.get_conversation(conversation_id) is None:
            raise HTTPException(404, "That conversation wasn't found.")
        try:
            return {"summarised": end_conversation(store, llm, settings.model, conversation_id)}
        except LLMError:
            # Not fatal: the note is written the next time the user signs in.
            return {"summarised": False}

    @app.post("/api/messages/{message_id}/feedback")
    def feedback(message_id: int, body: FeedbackIn, store=Depends(consented_store)):
        store.set_feedback(message_id, body.value)
        return {"ok": True}

    # chat (streamed) ---------------------------------------------------------------------------------------
    @app.post("/api/chat")
    def chat(body: ChatIn, store=Depends(consented_store)):
        text = body.message.strip()
        if not text:
            raise HTTPException(422, "Please type a message.")
        if store.count_user_messages_today() >= settings.daily_message_limit:
            raise HTTPException(429, "You've reached today's message limit. Come back tomorrow.")

        conversation_id = body.conversation_id
        if conversation_id:
            existing = store.get_conversation(conversation_id)
            if existing is None:
                raise HTTPException(404, "That conversation wasn't found.")
            if existing.get("summary"):
                store.clear_summary(conversation_id)  # it will be summarised again when it ends
        else:
            conversation_id = store.create_conversation()
        user_message_id = store.add_message(conversation_id, "user", text)

        documents, _ = select_for_prompt(store.list_documents())
        system = build_system_prompt(
            store.get_profile(), store.recent_summaries(SUMMARIES_IN_PROMPT), documents
        )
        history = to_api_messages(store.get_messages(conversation_id))

        def events():
            yield sse("meta", {"conversation_id": conversation_id, "user_message_id": user_message_id})
            reply = []
            try:
                for chunk in stream_reply(llm, settings.model, system, history):
                    reply.append(chunk)
                    yield sse("delta", {"text": chunk})
            except LLMRateLimitError:
                yield sse("error", {"message": "Compass is busy right now. Please try again in a minute."})
                return
            except LLMConnectionError:
                yield sse("error", {"message": "Couldn't reach the coaching service. Please try again."})
                return
            except LLMError as exc:
                code = f" ({exc.status_code})" if exc.status_code else ""
                yield sse("error", {"message": f"The coaching service returned an error{code}. Please try again."})
                return
            answer = "".join(reply)
            try:
                message_id = store.add_message(conversation_id, "assistant", answer)
            except Exception:
                log.exception("Couldn't save the coach reply")
                yield sse("error", {"message": "I couldn't save that reply to your history."})
                return
            yield sse("done", {"message_id": message_id})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # React app ------------------------------------------------------------------------------------------------
    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def unknown_api(rest: str):
        raise HTTPException(404, "Not found.")

    dist = Path(static_dir) if static_dir else Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")  # client-side routes (/documents, /privacy, ...)

    return app
