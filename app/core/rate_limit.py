"""Rate limiting.

Business code depends on the :class:`RateLimiter` protocol. A single node (and
the test suite) uses the in-process limiter; a multi-node deployment sets
``REDIS_URL`` and the container wires in the Redis-backed limiter, which shares
one fixed window across every instance.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
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
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()
        self._last_sweep = clock()

    @property
    def tracked(self) -> int:
        """How many identities are currently held in memory."""
        return len(self._hits)

    async def check(self, identity: str) -> tuple[bool, int]:
        now = self._clock()
        cutoff = now - self._window
        async with self._lock:
            self._sweep(now, cutoff)
            recent = [ts for ts in self._hits.get(identity, []) if ts > cutoff]
            if len(recent) >= self.limit:
                self._hits[identity] = recent
                return False, 0
            recent.append(now)
            self._hits[identity] = recent
            return True, self.limit - len(recent)

    def _sweep(self, now: float, cutoff: float) -> None:
        # Pruning an identity's own timestamps is not enough: without dropping
        # the key as well the map keeps one entry per address ever seen, which
        # on a public endpoint grows without bound. Sweeping once per window
        # keeps the request path off the O(identities) scan.
        if now - self._last_sweep < self._window:
            return
        self._last_sweep = now
        for key in [k for k, hits in self._hits.items() if not any(ts > cutoff for ts in hits)]:
            del self._hits[key]


class RedisRateLimiter:
    """Fixed-window limiter shared across nodes via Redis INCR + EXPIRE."""

    def __init__(self, client: Redis, *, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self._client = client
        self._window = window_seconds

    async def check(self, identity: str) -> tuple[bool, int]:
        key = f"ratelimit:{identity}"
        # One transaction, not two round trips: an INCR whose EXPIRE never
        # followed (a crash, a dropped connection) leaves a counter with no TTL,
        # and that identity is then blocked for good. NX keeps the window fixed
        # rather than sliding it forward on every hit.
        pipeline = self._client.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, self._window, nx=True)
        count = int((await pipeline.execute())[0])
        remaining = max(0, self.limit - count)
        return count <= self.limit, remaining
