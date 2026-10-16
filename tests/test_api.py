"""The HTTP API, through FastAPI's TestClient, with Supabase and the LLM faked."""

import json

import pytest
from fastapi.testclient import TestClient

from compass.api import create_app, sse
from compass.config import Settings
from compass.consent import CONSENT_VERSION
from compass.jwt_auth import AuthError, AuthUser
from compass.llm import LLMRateLimitError
from tests.fakes import FakeLLM, FakeStore
from tests.test_documents import make_docx, make_text_pdf

SETTINGS = Settings("k", "https://abc.supabase.co", "sb_publishable_x", daily_message_limit=50)
AUTH = {"Authorization": "Bearer tok-u1"}


class FakeVerifier:
    def verify(self, token):
        if token != "tok-u1":
            raise AuthError("Please sign in again.")
        return AuthUser("u1", "aun@example.com", token)


def make_client(store=None, llm=None, settings=SETTINGS, static_dir="/nonexistent"):
    store = store or FakeStore()
    llm = llm or FakeLLM()
    app = create_app(settings, verifier=FakeVerifier(), store_factory=lambda user: store, llm=llm, static_dir=static_dir)
    return TestClient(app, raise_server_exceptions=False), store, llm


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


# auth & config -----------------------------------------------------------------
def test_public_endpoints_need_no_login():
    client, *_ = make_client()
    assert client.get("/api/health").json() == {"ok": True}
    config = client.get("/api/config").json()
    assert config == {"supabase_url": "https://abc.supabase.co", "supabase_publishable_key": "sb_publishable_x"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic tok-u1"}, {"Authorization": "Bearer"}])
def test_every_data_endpoint_rejects_missing_or_bad_tokens(headers):
    client, *_ = make_client()
    for method, path in [("get", "/api/bootstrap"), ("get", "/api/profile"), ("post", "/api/chat"),
                         ("get", "/api/documents"), ("delete", "/api/me/data")]:
        response = getattr(client, method)(path, headers=headers)
        assert response.status_code == 401, (method, path)


def test_unknown_api_routes_are_404_json():
    client, *_ = make_client()
    response = client.get("/api/nope", headers=AUTH)
    assert response.status_code == 404 and "detail" in response.json()


# consent -----------------------------------------------------------------------
def test_nothing_is_available_before_consent():
    client, store, llm = make_client(FakeStore(consented=False))
    boot = client.get("/api/bootstrap", headers=AUTH).json()
    assert boot["consent"]["accepted"] is False and boot["consent"]["current_version"] == CONSENT_VERSION
    assert "profile" not in boot and "documents" not in boot and "conversations" not in boot
    for method, path in [("get", "/api/profile"), ("get", "/api/documents"), ("get", "/api/conversations")]:
        assert getattr(client, method)(path, headers=AUTH).status_code == 403
    assert client.post("/api/chat", json={"message": "hi"}, headers=AUTH).status_code == 403
    assert llm.stream_calls == [] and store.conversations == {}


def test_consent_must_be_agreed_and_records_training_choice_separately():
    client, store, _ = make_client(FakeStore(consented=False))
    assert client.post("/api/consent", json={"agree": False}, headers=AUTH).status_code == 422
    assert store.consent == {}
    assert client.post("/api/consent", json={"agree": True}, headers=AUTH).status_code == 200
    assert store.consent == {"version": CONSENT_VERSION, "training_opt_in": False}  # default off
    client.post("/api/consent", json={"agree": True, "training_opt_in": True}, headers=AUTH)
    assert store.consent["training_opt_in"] is True
    assert client.get("/api/bootstrap", headers=AUTH).json()["consent"]["accepted"] is True


def test_outdated_consent_asks_again_and_training_opt_in_can_change():
    store = FakeStore()
    store.consent = {"version": "old", "training_opt_in": True}
    client, *_ = make_client(store)
    boot = client.get("/api/bootstrap", headers=AUTH).json()
    assert boot["consent"]["accepted"] is False and boot["consent"]["training_opt_in"] is False
    store.consent = {"version": CONSENT_VERSION, "training_opt_in": False}
    assert client.put("/api/consent/training", json={"opted_in": True}, headers=AUTH).json() == {"training_opt_in": True}
    assert store.consent["training_opt_in"] is True


# profile -------------------------------------------------------------------------
def test_profile_round_trip_and_limits():
    client, store, _ = make_client()
    saved = client.put("/api/profile", json={"role": "Analyst", "goals": "Lead a team"}, headers=AUTH).json()
    assert saved == {"role": "Analyst", "industry": "", "goals": "Lead a team", "cv_text": ""}
    assert client.get("/api/profile", headers=AUTH).json() == saved
    too_long = client.put("/api/profile", json={"role": "x" * 201}, headers=AUTH)
    assert too_long.status_code == 422


# chat ------------------------------------------------------------------------------
def test_chat_streams_saves_both_messages_and_returns_ids():
    client, store, llm = make_client()
    store.save_profile(role="Analyst")
    response = client.post("/api/chat", json={"message": "How do I get promoted?"}, headers=AUTH)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [e for e, _ in events] == ["meta", "delta", "delta", "done"]
    assert "".join(d["text"] for e, d in events if e == "delta") == "Hello there."
    meta, done = events[0][1], events[-1][1]
    saved = store.conversations[meta["conversation_id"]]["messages"]
    assert [(m["role"], m["content"]) for m in saved] == [("user", "How do I get promoted?"), ("assistant", "Hello there.")]
    assert saved[0]["id"] == meta["user_message_id"] and saved[1]["id"] == done["message_id"]
    assert "Current role:\nAnalyst" in llm.stream_calls[0]["messages"][0]["content"]


def test_chat_continues_an_existing_conversation_and_clears_its_stale_summary():
    client, store, llm = make_client()
    first = parse_sse(client.post("/api/chat", json={"message": "one"}, headers=AUTH).text)
    cid = first[0][1]["conversation_id"]
    store.set_summary(cid, "- old note")
    again = parse_sse(client.post("/api/chat", json={"message": "two", "conversation_id": cid}, headers=AUTH).text)
    assert again[0][1]["conversation_id"] == cid and store.conversations[cid]["summary"] is None
    roles = [m["role"] for m in llm.stream_calls[-1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]  # the model sees the earlier turns


def test_chat_rejects_unknown_conversation_empty_and_oversized_messages():
    client, store, llm = make_client()
    assert client.post("/api/chat", json={"message": "hi", "conversation_id": "nope"}, headers=AUTH).status_code == 404
    assert client.post("/api/chat", json={"message": "   "}, headers=AUTH).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 8001}, headers=AUTH).status_code == 422
    assert llm.stream_calls == [] and store.conversations == {}


def test_daily_limit_blocks_before_anything_is_saved_or_sent():
    store = FakeStore()
    store.today = 50
    client, store, llm = make_client(store)
    response = client.post("/api/chat", json={"message": "hi"}, headers=AUTH)
    assert response.status_code == 429 and "limit" in response.json()["detail"]
    assert llm.stream_calls == [] and store.conversations == {}


def test_enabled_documents_reach_the_prompt_and_disabled_ones_do_not():
    store = FakeStore()
    store.add_document("review.docx", "Q3 review: strong delivery, weak visibility.", False)
    store.add_document("old-cv.pdf", "Ancient history.", False)
    store.set_document_enabled("d2", False)
    client, _, llm = make_client(store)
    client.post("/api/chat", json={"message": "How do I get visible?"}, headers=AUTH)
    system = llm.stream_calls[0]["messages"][0]["content"]
    assert '<document name="review.docx">' in system and "weak visibility" in system
    assert "old-cv.pdf" not in system


def test_model_errors_become_error_events_and_the_user_message_is_kept():
    class Failing(FakeLLM):
        def stream_chat(self, *a, **k):
            raise LLMRateLimitError("slow down", 429)
            yield  # pragma: no cover

    client, store, _ = make_client(llm=Failing())
    events = parse_sse(client.post("/api/chat", json={"message": "hi"}, headers=AUTH).text)
    assert [e for e, _ in events] == ["meta", "error"] and "busy" in events[1][1]["message"]
    [conv] = store.conversations.values()
    assert [m["role"] for m in conv["messages"]] == ["user"]  # no half-saved assistant reply


# sessions, history, feedback -------------------------------------------------------------
def test_end_session_writes_a_summary_used_by_the_next_conversation():
    client, store, llm = make_client()
    cid = parse_sse(client.post("/api/chat", json={"message": "hi"}, headers=AUTH).text)[0][1]["conversation_id"]
    assert client.post(f"/api/conversations/{cid}/end", headers=AUTH).json() == {"summarised": True}
    assert store.conversations[cid]["summary"]
    client.post("/api/chat", json={"message": "hi again"}, headers=AUTH)
    assert "- a\n- b" in llm.stream_calls[-1]["messages"][0]["content"]
    assert client.post("/api/conversations/missing/end", headers=AUTH).status_code == 404


def test_conversation_history_lists_and_reopens_with_feedback():
    client, store, _ = make_client()
    cid = parse_sse(client.post("/api/chat", json={"message": "First question"}, headers=AUTH).text)[0][1]["conversation_id"]
    listing = client.get("/api/conversations", headers=AUTH).json()["items"]
    assert listing[0]["id"] == cid and listing[0]["title"] == "First question"
    detail = client.get(f"/api/conversations/{cid}", headers=AUTH).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assistant_id = detail["messages"][1]["id"]
    assert client.post(f"/api/messages/{assistant_id}/feedback", json={"value": 1}, headers=AUTH).status_code == 200
    assert client.get(f"/api/conversations/{cid}", headers=AUTH).json()["messages"][1]["feedback"] == 1
    client.post(f"/api/messages/{assistant_id}/feedback", json={"value": None}, headers=AUTH)
    assert client.get(f"/api/conversations/{cid}", headers=AUTH).json()["messages"][1]["feedback"] is None
    assert client.post(f"/api/messages/{assistant_id}/feedback", json={"value": 5}, headers=AUTH).status_code == 422
    assert client.get("/api/conversations/nope", headers=AUTH).status_code == 404


def test_bootstrap_returns_everything_and_starts_catch_up():
    store = FakeStore()
    old = store.create_conversation()
    store.add_message(old, "user", "hi")
    store.add_message(old, "assistant", "hello")
    store.save_profile(role="Analyst")
    store.add_document("cv.pdf", "my cv", False)
    client, _, _ = make_client(store)
    boot = client.get("/api/bootstrap", headers=AUTH).json()
    assert boot["user"] == {"id": "u1", "email": "aun@example.com"}
    assert boot["profile"]["role"] == "Analyst"
    assert boot["documents"]["items"][0]["name"] == "cv.pdf" and "content" not in boot["documents"]["items"][0]
    assert boot["conversations"][0]["id"] == old
    assert store.conversations[old]["summary"]  # earlier session summarised in the background


# documents --------------------------------------------------------------------------------
def test_document_upload_toggle_and_remove():
    client, store, _ = make_client()
    files = [
        ("files", ("notes.txt", b"Goal: lead a team", "text/plain")),
        ("files", ("cv.pdf", make_text_pdf("Senior analyst"), "application/pdf")),
        ("files", ("review.docx", make_docx(["Strong delivery"]), "application/octet-stream")),
        ("files", ("virus.exe", b"MZ", "application/octet-stream")),
        ("files", ("empty.txt", b"  ", "text/plain")),
    ]
    body = client.post("/api/documents", files=files, headers=AUTH).json()
    assert [(r["name"], r["ok"]) for r in body["results"]] == [
        ("notes.txt", True), ("cv.pdf", True), ("review.docx", True), ("virus.exe", False), ("empty.txt", False)]
    assert "PDF, Word" in body["results"][3]["error"] and "any text" in body["results"][4]["error"]
    assert len(body["items"]) == 3 and body["budget"]["used"] > 0
    assert all("content" not in item for item in body["items"])

    doc_id = body["items"][0]["id"]
    patched = client.patch(f"/api/documents/{doc_id}", json={"enabled": False}, headers=AUTH).json()
    assert [i["enabled"] for i in patched["items"] if i["id"] == doc_id] == [False]
    removed = client.delete(f"/api/documents/{doc_id}", headers=AUTH).json()
    assert len(removed["items"]) == 2


def test_document_count_limit_is_enforced():
    client, store, _ = make_client()
    for i in range(10):
        store.add_document(f"d{i}.txt", "x" * 50, False)
    body = client.post("/api/documents", files=[("files", ("one-more.txt", b"hello", "text/plain"))], headers=AUTH).json()
    assert body["results"][0]["ok"] is False and "up to 10" in body["results"][0]["error"]


# privacy ----------------------------------------------------------------------------------
def test_delete_my_data_requires_the_confirmation_word():
    client, store, _ = make_client()
    cid = store.create_conversation()
    store.add_message(cid, "user", "hi")
    assert client.request("DELETE", "/api/me/data", json={"confirm": "delete"}, headers=AUTH).status_code == 422
    assert client.request("DELETE", "/api/me/data", headers=AUTH).status_code == 422
    assert not store.deleted
    assert client.request("DELETE", "/api/me/data", json={"confirm": "DELETE"}, headers=AUTH).status_code == 200
    assert store.deleted and store.conversations == {}


# robustness ----------------------------------------------------------------------------------
def test_unexpected_errors_are_generic_json_without_leaking_details():
    class Broken(FakeStore):
        def get_profile(self):
            raise RuntimeError("secret database detail")

    client, *_ = make_client(Broken())
    response = client.get("/api/profile", headers=AUTH)
    assert response.status_code == 500 and "secret" not in response.text
    assert response.json()["detail"].startswith("Something went wrong")


def test_sse_helper_keeps_unicode_and_one_line_per_event():
    frame = sse("delta", {"text": "Café\nnewline"})
    assert frame == 'event: delta\ndata: {"text": "Café\\nnewline"}\n\n'


# serving the React build ----------------------------------------------------------------------
def test_spa_fallback_serves_index_for_client_routes_but_not_api(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    client, *_ = make_client(static_dir=tmp_path)
    assert client.get("/documents").text == "<html>app</html>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/../../etc/passwd").text == "<html>app</html>"  # no path traversal
    assert client.get("/api/missing").status_code == 404


def test_security_headers_and_no_caching_of_api_responses():
    client, *_ = make_client()
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "connect-src 'self' https://abc.supabase.co" in csp
    assert "script-src" not in csp or "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
