"""Rate limiting.

Business code depends on the :class:`RateLimiter` protocol. A single node (and
the test suite) uses the in-process limiter; a multi-node deployment sets
``REDIS_URL`` and the container wires in the Redis-backed limiter, which shares
one fixed window across every instance.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redis.asyncio import Redis


@runtime_checkable
class RateLimiter(Protocol):
    limit: int

    async def check(self, identity: str) -> tuple[bool, int]:
        """Return ``(allowed, remaining)`` for the caller identity."""
        ...


class InMemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, identity: str) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - self._window
        async with self._lock:
            recent = [ts for ts in self._hits[identity] if ts > cutoff]
            if len(recent) >= self.limit:
                self._hits[identity] = recent
                return False, 0
            recent.append(now)
            self._hits[identity] = recent
            return True, self.limit - len(recent)


class RedisRateLimiter:
    """Fixed-window limiter shared across nodes via Redis INCR + EXPIRE."""

    def __init__(self, client: Redis, *, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self._client = client
        self._window = window_seconds

    async def check(self, identity: str) -> tuple[bool, int]:
        key = f"ratelimit:{identity}"
        count = int(await self._client.incr(key))
        if count == 1:
            await self._client.expire(key, self._window)
        remaining = max(0, self.limit - count)
        return count <= self.limit, remaining
