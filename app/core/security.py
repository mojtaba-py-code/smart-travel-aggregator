"""Password hashing (Argon2id) and JWT access/refresh token handling.

Argon2id is the current OWASP recommendation for password storage. Tokens are
short-lived access + longer-lived refresh, each tagged with a ``type`` claim so
a refresh token can never be replayed as an access token.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings

TokenType = Literal["access", "refresh"]

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when the stored hash uses out-of-date parameters and should be upgraded."""
    return _hasher.check_needs_rehash(hashed)


def _create_token(
    *, subject: str, token_type: TokenType, ttl: int, settings: Settings
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, settings: Settings) -> str:
    return _create_token(
        subject=subject,
        token_type="access",
        ttl=settings.access_token_ttl,
        settings=settings,
    )


def create_refresh_token(subject: str, settings: Settings) -> str:
    return _create_token(
        subject=subject,
        token_type="refresh",
        ttl=settings.refresh_token_ttl,
        settings=settings,
    )


class TokenError(Exception):
    """Raised when a token is missing, expired, malformed or of the wrong type."""


def decode_token(token: str, *, expected_type: TokenType, settings: Settings) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("token is invalid") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"expected a {expected_type} token")
    if "sub" not in payload:
        raise TokenError("token is missing a subject")
    return payload
