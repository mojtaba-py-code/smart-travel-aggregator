"""Token blocklist behaviour."""

from __future__ import annotations

import time

from app.resilience.cache import InMemoryCache
from app.services.token_blocklist import TokenBlocklist


async def test_revoke_and_check() -> None:
    blocklist = TokenBlocklist(InMemoryCache())
    payload = {"jti": "abc", "exp": int(time.time()) + 100}

    assert await blocklist.is_revoked(payload) is False
    await blocklist.revoke(payload)
    assert await blocklist.is_revoked(payload) is True


async def test_expired_token_is_not_stored() -> None:
    blocklist = TokenBlocklist(InMemoryCache())
    already_expired = {"jti": "old", "exp": int(time.time()) - 5}
    await blocklist.revoke(already_expired)
    # Nothing to store for a token that is already expired.
    assert await blocklist.is_revoked(already_expired) is False


async def test_payload_without_jti_is_ignored() -> None:
    blocklist = TokenBlocklist(InMemoryCache())
    await blocklist.revoke({"exp": int(time.time()) + 100})
    assert await blocklist.is_revoked({"exp": int(time.time()) + 100}) is False
