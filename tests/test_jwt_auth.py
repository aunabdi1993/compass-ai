import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from compass.jwt_auth import AuthError, JWTVerifier

ISSUER = "https://abc.supabase.co/auth/v1"


class FakeJWKS:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self.public_key)


@pytest.fixture(scope="module")
def keys():
    return ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())


def token(key, **overrides):
    claims = {"sub": "user-1", "email": "a@example.com", "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 600}
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="ES256")


def verifier(keys):
    return JWTVerifier("unused", ISSUER, jwk_client=FakeJWKS(keys[0].public_key()))


def test_valid_token_gives_user_and_keeps_the_token(keys):
    t = token(keys[0])
    user = verifier(keys).verify(t)
    assert (user.id, user.email, user.token) == ("user-1", "a@example.com", t)


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"exp": int(time.time()) - 10}, "expired"),
        ({"aud": "anon"}, "sign in"),
        ({"iss": "https://evil.example/auth/v1"}, "sign in"),
        ({"sub": None}, "sign in"),
    ],
)
def test_rejects_expired_wrong_audience_issuer_or_missing_subject(keys, overrides, message):
    with pytest.raises(AuthError, match=message):
        verifier(keys).verify(token(keys[0], **overrides))


def test_rejects_tokens_signed_by_another_key_and_garbage(keys):
    with pytest.raises(AuthError):
        verifier(keys).verify(token(keys[1]))
    with pytest.raises(AuthError):
        verifier(keys).verify("not.a.jwt")


def test_rejects_unsigned_and_hmac_tokens(keys):
    unsigned = jwt.encode({"sub": "u", "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 60}, key=None, algorithm="none")
    with pytest.raises(AuthError):
        verifier(keys).verify(unsigned)
    hs = jwt.encode({"sub": "u", "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 60}, "x" * 40, algorithm="HS256")
    with pytest.raises(AuthError):
        verifier(keys).verify(hs)  # algorithm-confusion attempts are refused


def test_unreachable_jwks_is_a_sign_in_error_not_a_crash():
    class Down:
        def get_signing_key_from_jwt(self, token):
            raise jwt.PyJWKClientConnectionError("offline")

    with pytest.raises(AuthError):
        JWTVerifier("unused", ISSUER, jwk_client=Down()).verify("a.b.c")
