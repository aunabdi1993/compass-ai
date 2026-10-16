"""Settings, read from environment variables (a local .env file is loaded by compass.server)."""

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "meta-llama/llama-4-maverick"  # OpenRouter slug
BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_DAILY_MESSAGE_LIMIT = 50


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    supabase_url: str
    supabase_key: str  # publishable (formerly anon) key, never the secret key
    model: str = DEFAULT_MODEL
    daily_message_limit: int = DEFAULT_DAILY_MESSAGE_LIMIT
    site_url: str | None = None
    jwks_url: str | None = None

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def jwks_endpoint(self) -> str:
        return self.jwks_url or f"{self.jwt_issuer}/.well-known/jwks.json"


def load_dotenv_file(path: str | Path = ".env") -> None:
    """Load KEY=value lines from a .env file into the environment (existing variables win)."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip("\"'")
        os.environ.setdefault(key.strip(), value)


def _is_privileged_key(key: str) -> bool:
    """True for Supabase secret / service_role keys, which bypass Row Level Security."""
    if key.startswith("sb_secret_"):
        return True
    try:  # legacy JWT-style keys carry a "role" claim
        payload = key.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return claims.get("role") == "service_role"
    except Exception:
        return False


def load_settings(env=None) -> Settings:
    env = os.environ if env is None else env

    def get(name):
        value = env.get(name)
        return str(value).strip() if value else None

    values = {name: get(name) for name in ("OPENROUTER_API_KEY", "SUPABASE_URL")}
    # SUPABASE_ANON_KEY is the legacy name for the publishable key.
    values["SUPABASE_PUBLISHABLE_KEY"] = get("SUPABASE_PUBLISHABLE_KEY") or get("SUPABASE_ANON_KEY")
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing configuration: " + ", ".join(missing) + ". Put them in a file named .env in the project folder "
            "(copy .env.example to .env and fill it in; .env.example itself is only a template and is not read), "
            "or set them as environment variables."
        )
    if _is_privileged_key(values["SUPABASE_PUBLISHABLE_KEY"]):
        raise RuntimeError(
            "The Supabase key is a secret/service-role key. Use the publishable key "
            "(SUPABASE_PUBLISHABLE_KEY): secret keys bypass Row Level Security."
        )
    return Settings(
        openrouter_api_key=values["OPENROUTER_API_KEY"],
        supabase_url=values["SUPABASE_URL"],
        supabase_key=values["SUPABASE_PUBLISHABLE_KEY"],
        model=get("COMPASS_MODEL") or DEFAULT_MODEL,
        daily_message_limit=int(get("MAX_USER_MESSAGES_PER_DAY") or DEFAULT_DAILY_MESSAGE_LIMIT),
        site_url=get("COMPASS_SITE_URL"),
        jwks_url=get("SUPABASE_JWKS_URL"),
    )
