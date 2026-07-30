"""Authentication use-cases.

Owns the security-sensitive rules — unique email, credential verification,
password rehash-on-login, email verification, password reset and logout
(token revocation) — and keeps the API layer thin.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.errors import AuthenticationError, ConflictError
from app.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    create_reset_token,
    create_verify_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.db.models import User
from app.repositories.users import UserRepository
from app.services.notifications import Notifier
from app.services.token_blocklist import TokenBlocklist


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        settings: Settings,
        *,
        notifier: Notifier,
        blocklist: TokenBlocklist,
    ) -> None:
        self._users = users
        self._settings = settings
        self._notifier = notifier
        self._blocklist = blocklist

    # -- registration & verification ---------------------------------------
    async def register(self, *, email: str, password: str, full_name: str | None) -> User:
        if await self._users.exists_by_email(email):
            raise ConflictError("an account with this email already exists")
        user = await self._users.create(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
        )
        await self._send_verification(user)
        return user

    async def resend_verification(self, email: str) -> None:
        user = await self._users.get_by_email(email)
        # Do not reveal whether the address exists or is already verified.
        if user is not None and not user.is_verified:
            await self._send_verification(user)

    async def verify_email(self, token: str) -> None:
        payload = self._decode(token, "verify")
        user = await self._users.get_by_id(uuid.UUID(payload["sub"]))
        if user is None:
            raise AuthenticationError("the account no longer exists")
        if not user.is_verified:
            await self._users.mark_verified(user)

    async def _send_verification(self, user: User) -> None:
        token = create_verify_token(str(user.id), self._settings)
        await self._notifier.send(
            to=user.email,
            subject="Verify your Smart Travel account",
            body=(
                "Welcome! Confirm your email to activate your account. "
                f"Verification token: {token}"
            ),
        )

    # -- login / refresh ---------------------------------------------------
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
        payload = self._decode(refresh_token, "refresh")
        if await self._blocklist.is_revoked(payload):
            raise AuthenticationError("this session has been revoked")
        user = await self._users.get_by_id(uuid.UUID(payload["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("the account is no longer valid")
        return self.issue_tokens(user)

    # -- password reset ----------------------------------------------------
    async def request_password_reset(self, email: str) -> None:
        user = await self._users.get_by_email(email)
        # Always succeed silently so callers cannot probe for valid addresses.
        if user is None or not user.is_active:
            return
        token = create_reset_token(str(user.id), self._settings)
        await self._notifier.send(
            to=user.email,
            subject="Reset your Smart Travel password",
            body=f"Use this token to set a new password: {token}",
        )

    async def reset_password(self, token: str, new_password: str) -> None:
        payload = self._decode(token, "reset")
        user = await self._users.get_by_id(uuid.UUID(payload["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("the account is no longer valid")
        await self._users.update_password(user, hash_password(new_password))

    # -- logout ------------------------------------------------------------
    async def logout(self, access_payload: dict[str, Any], refresh_token: str | None) -> None:
        await self._blocklist.revoke(access_payload)
        if refresh_token:
            try:
                refresh_payload = decode_token(
                    refresh_token, expected_type="refresh", settings=self._settings
                )
            except TokenError:
                return
            await self._blocklist.revoke(refresh_payload)

    # -- helpers -----------------------------------------------------------
    def _decode(self, token: str, expected: TokenType) -> dict[str, Any]:
        try:
            return decode_token(token, expected_type=expected, settings=self._settings)
        except TokenError as exc:
            raise AuthenticationError(str(exc)) from exc


# A pre-computed Argon2 hash of a random value; only used so that authenticating
# a non-existent user still performs a hash verification (constant-ish time).
_DUMMY_HASH = hash_password("this-is-never-a-real-password")
