"""Consent versioning. The consent wording itself lives in the React app (frontend/src/pages/Consent.tsx);
bump CONSENT_VERSION when it changes to ask every user again."""

CONSENT_VERSION = "2026-10-v1"


def needs_consent(consent: dict | None) -> bool:
    return not consent or consent.get("version") != CONSENT_VERSION
