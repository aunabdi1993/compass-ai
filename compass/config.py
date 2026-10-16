"""Settings, read from Streamlit secrets with an environment-variable fallback."""

import os
from dataclasses import dataclass

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_DAILY_MESSAGE_LIMIT = 50


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    supabase_url: str
    supabase_anon_key: str
    model: str = DEFAULT_MODEL
    daily_message_limit: int = DEFAULT_DAILY_MESSAGE_LIMIT


def _lookup(name, secrets):
    try:
        if name in secrets:
            return str(secrets[name])
    except Exception:  # no secrets.toml at all
        pass
    return os.environ.get(name)


def load_settings(secrets=None) -> Settings:
    secrets = secrets if secrets is not None else {}
    values = {
        name: _lookup(name, secrets)
        for name in ("ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY")
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing configuration: "
            + ", ".join(missing)
            + ". Set them in .streamlit/secrets.toml or as environment variables."
        )
    return Settings(
        anthropic_api_key=values["ANTHROPIC_API_KEY"],
        supabase_url=values["SUPABASE_URL"],
        supabase_anon_key=values["SUPABASE_ANON_KEY"],
        model=_lookup("COMPASS_MODEL", secrets) or DEFAULT_MODEL,
        daily_message_limit=int(
            _lookup("MAX_USER_MESSAGES_PER_DAY", secrets) or DEFAULT_DAILY_MESSAGE_LIMIT
        ),
    )
