"""Authentication use-cases: registration, login and token refresh.

The service owns the security-sensitive rules (unique email, credential
verification, password rehash-on-login) and keeps the API layer thin.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AuthenticationError, ConflictError
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.db.models import User
from app.repositories.users import UserRepository


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthService:
    def __init__(self, users: UserRepository, settings: Settings) -> None:
        self._users = users
        self._settings = settings

    async def register(
        self, *, email: str, password: str, full_name: str | None
    ) -> User:
        if await self._users.exists_by_email(email):
            raise ConflictError("an account with this email already exists")
        return await self._users.create(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
        )

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self._users.get_by_email(email)
        # Verify against a real or dummy hash either way to blunt user enumeration
        # via response-timing differences.
        stored = user.hashed_password if user else _DUMMY_HASH
        password_ok = verify_password(password, stored)

        if user is None or not password_ok:
            raise AuthenticationError("incorrect email or password")
        if not user.is_active:
            raise AuthenticationError("this account is disabled")

        if needs_rehash(user.hashed_password):
            await self._users.update_password(user, hash_password(password))
        return user

    def issue_tokens(self, user: User) -> TokenPair:
        subject = str(user.id)
        return TokenPair(
            access_token=create_access_token(subject, self._settings),
            refresh_token=create_refresh_token(subject, self._settings),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            payload = decode_token(
                refresh_token, expected_type="refresh", settings=self._settings
            )
        except TokenError as exc:
            raise AuthenticationError(str(exc)) from exc
        user = await self._users.get_by_id(uuid.UUID(payload["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("the account is no longer valid")
        return self.issue_tokens(user)


# A pre-computed Argon2 hash of a random value; only used so that authenticating
# a non-existent user still performs a hash verification (constant-ish time).
_DUMMY_HASH = hash_password("this-is-never-a-real-password")
