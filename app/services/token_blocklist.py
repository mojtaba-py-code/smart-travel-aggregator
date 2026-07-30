"""Token revocation (denylist) for logout.

JWTs are stateless, so "logging out" means recording a token's unique id
(``jti``) as revoked until it would have expired anyway. Backed by the shared
cache (Redis in production, in-memory in dev/tests), so entries expire on their
own and never grow unbounded.
"""

from __future__ import annotations

import time
from typing import Any

from app.resilience.cache import Cache


class TokenBlocklist:
    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    async def revoke(self, payload: dict[str, Any]) -> None:
        jti = payload.get("jti")
        if not jti:
            return
        ttl = self._remaining_ttl(payload)
        if ttl > 0:
            await self._cache.set(f"revoked:{jti}", "1", ttl)

    async def is_revoked(self, payload: dict[str, Any]) -> bool:
        jti = payload.get("jti")
        if not jti:
            return False
        return await self._cache.get(f"revoked:{jti}") is not None

    @staticmethod
    def _remaining_ttl(payload: dict[str, Any]) -> int:
        exp = payload.get("exp")
        if not isinstance(exp, int):
            return 0
        return max(0, exp - int(time.time()))
