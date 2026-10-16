"""A local Compass stack with no cloud accounts: the real API + built React app, a fake Supabase
sign-in (issues genuine ES256 JWTs and serves a JWKS the API really verifies against), an in-memory
database and a scripted coach.

    cd frontend && npm run build && cd ..
    python -m uvicorn e2e.fake_stack:app --port 8700
    # open http://localhost:8700 and sign in with any email and any code

Used by e2e/run_browser_check.py. Not for production: data lives in memory and any code is accepted.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from jwt.algorithms import ECAlgorithm

from compass.api import create_app
from compass.config import Settings
from tests.fakes import FakeLLM, FakeStore

PORT = 8700
URL = f"http://localhost:{PORT}"
KEY = ec.generate_private_key(ec.SECP256R1())
KID = "e2e-key"
store = FakeStore(consented=False)  # new users must pass the consent screen first
store.add_document("performance-review-2025.docx", "Strong delivery. Needs more visibility. " * 30, False)


class SlowLLM(FakeLLM):
    """Streams a realistic markdown reply a few words at a time."""

    REPLY = (
        "Thanks for sharing that. To help, I'd like to understand two things:\n\n"
        "1. What does **\"strategic\"** look like in your manager's own words?\n"
        "2. Can you give an example of recent work they called *tactical*?\n\n"
        "**Next steps this week:**\n\n- Ask your manager for one example of strategic work\n- Note what they say\n"
    ).split(" ")

    def stream_chat(self, model, messages, max_tokens):
        self.stream_calls.append({"model": model, "messages": messages})
        yield {"choices": []}
        for word in self.REPLY:
            time.sleep(0.06)
            yield {"choices": [{"delta": {"content": word + " "}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}


def make_session(email: str) -> dict:
    now = int(time.time())
    token = jwt.encode(
        {"sub": "user-e2e", "email": email, "aud": "authenticated", "role": "authenticated",
         "iss": f"{URL}/auth/v1", "iat": now, "exp": now + 3600},
        KEY, algorithm="ES256", headers={"kid": KID},
    )
    return {
        "access_token": token, "token_type": "bearer", "expires_in": 3600, "expires_at": now + 3600,
        "refresh_token": "refresh-e2e",
        "user": {"id": "user-e2e", "aud": "authenticated", "role": "authenticated", "email": email,
                 "app_metadata": {}, "user_metadata": {}, "created_at": "2026-10-01T00:00:00Z"},
    }


settings = Settings("key", URL, "sb_publishable_e2e", daily_message_limit=50)
compass = create_app(settings, store_factory=lambda user: store, llm=SlowLLM())

app = FastAPI()  # the fake Supabase sits in front; everything else goes to the real Compass app
last_email = {"value": "aun@example.com"}


@app.post("/auth/v1/otp")
async def otp(request: Request):
    body = await request.json()
    last_email["value"] = body.get("email", last_email["value"])
    return {}


@app.post("/auth/v1/verify")
async def verify(request: Request):
    body = await request.json()
    last_email["value"] = body.get("email", last_email["value"])
    return make_session(last_email["value"])


@app.post("/auth/v1/token")
async def refresh():
    return make_session(last_email["value"])


@app.get("/auth/v1/user")
async def user():
    return make_session(last_email["value"])["user"]


@app.post("/auth/v1/logout")
async def logout():
    return Response(status_code=204)


@app.get("/auth/v1/.well-known/jwks.json")
async def jwks():
    jwk = ECAlgorithm.to_jwk(KEY.public_key(), as_dict=True) | {"kid": KID, "use": "sig", "alg": "ES256"}
    return JSONResponse({"keys": [jwk]})


app.mount("/", compass)
