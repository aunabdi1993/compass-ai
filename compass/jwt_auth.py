"""Verify the Supabase access token the React app sends with every API call."""

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

# Supabase signs with an asymmetric key (published at the project's JWKS URL).
ALGORITHMS = ["ES256", "RS256", "EdDSA"]


class AuthError(Exception):
    """The request has no valid sign-in. The message is safe to show."""


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    token: str  # the user's own JWT, used to talk to the database under Row Level Security


class JWTVerifier:
    def __init__(self, jwks_url: str, issuer: str, audience: str = "authenticated", jwk_client=None):
        self._jwks = jwk_client or PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> AuthUser:
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("Your session has expired. Please sign in again.") from exc
        except (jwt.PyJWTError, OSError) as exc:  # bad token, unknown key, or JWKS unreachable
            raise AuthError("Please sign in again.") from exc
        return AuthUser(id=claims["sub"], email=claims.get("email", ""), token=token)
