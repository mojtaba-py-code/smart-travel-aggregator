"""Password hashing and JWT handling."""

from __future__ import annotations

import time

import pytest

from app.core.config import Settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(secret_key="unit-test-secret-key-long-enough-000000")


def test_password_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_rejects_garbage_hash() -> None:
    assert verify_password("anything", "not-a-valid-argon2-hash") is False


def test_access_token_round_trip(settings: Settings) -> None:
    token = create_access_token("user-123", settings)
    payload = decode_token(token, expected_type="access", settings=settings)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_cannot_be_used_as_access(settings: Settings) -> None:
    token = create_refresh_token("user-123", settings)
    with pytest.raises(TokenError):
        decode_token(token, expected_type="access", settings=settings)


def test_expired_token_is_rejected(settings: Settings) -> None:
    short = Settings(secret_key=settings.secret_key, access_token_ttl=-1)
    token = create_access_token("user-123", short)
    time.sleep(0.01)
    with pytest.raises(TokenError):
        decode_token(token, expected_type="access", settings=short)


def test_tampered_token_is_rejected(settings: Settings) -> None:
    token = create_access_token("user-123", settings)
    with pytest.raises(TokenError):
        decode_token(token + "x", expected_type="access", settings=settings)
