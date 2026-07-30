"""A lightweight fixed-window rate limiter.

Keyed by client identity (IP by default). The in-process implementation is
fine for a single node and for tests; a multi-node deployment would back this
with Redis using the same interface.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, *, limit: int, window_seconds: int = 60) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, identity: str) -> tuple[bool, int]:
        """Return ``(allowed, remaining)`` for the caller identity."""
        now = time.monotonic()
        cutoff = now - self._window
        async with self._lock:
            recent = [ts for ts in self._hits[identity] if ts > cutoff]
            if len(recent) >= self._limit:
                self._hits[identity] = recent
                return False, 0
            recent.append(now)
            self._hits[identity] = recent
            return True, self._limit - len(recent)

    @property
    def limit(self) -> int:
        return self._limit
