"""Settings, read from Streamlit secrets with an environment-variable fallback."""

import base64
import json
import os
from dataclasses import dataclass

DEFAULT_MODEL = "meta-llama/llama-4-maverick"  # OpenRouter slug
BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_DAILY_MESSAGE_LIMIT = 50


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    supabase_url: str
    supabase_key: str  # publishable (formerly anon) key, never the secret key
    model: str = DEFAULT_MODEL
    site_url: str | None = None
    daily_message_limit: int = DEFAULT_DAILY_MESSAGE_LIMIT


def _lookup(name, secrets):
    try:
        if name in secrets:
            return str(secrets[name])
    except Exception:  # no secrets.toml at all
        pass
    return os.environ.get(name)


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


def load_settings(secrets=None) -> Settings:
    secrets = secrets if secrets is not None else {}
    values = {
        name: _lookup(name, secrets) for name in ("OPENROUTER_API_KEY", "SUPABASE_URL")
    }
    # SUPABASE_ANON_KEY is the legacy name for the publishable key.
    values["SUPABASE_PUBLISHABLE_KEY"] = _lookup("SUPABASE_PUBLISHABLE_KEY", secrets) or _lookup(
        "SUPABASE_ANON_KEY", secrets
    )
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing configuration: "
            + ", ".join(missing)
            + ". Set them in .streamlit/secrets.toml or as environment variables."
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
        model=_lookup("COMPASS_MODEL", secrets) or DEFAULT_MODEL,
        site_url=_lookup("COMPASS_SITE_URL", secrets),
        daily_message_limit=int(
            _lookup("MAX_USER_MESSAGES_PER_DAY", secrets) or DEFAULT_DAILY_MESSAGE_LIMIT
        ),
    )
