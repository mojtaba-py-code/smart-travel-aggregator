"""A minimal async circuit breaker.

States: CLOSED (normal) -> OPEN (failing, calls short-circuit) -> HALF_OPEN
(probing). After ``failure_threshold`` consecutive failures the breaker opens
and rejects calls for ``recovery_seconds``; the next call then probes the
upstream and either closes the breaker (success) or re-opens it (failure).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when a call is rejected because the breaker is open."""

    def __init__(self, name: str) -> None:
        super().__init__(f"circuit breaker '{name}' is open")
        self.name = name


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._clock = clock or asyncio.get_event_loop().time
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            self._maybe_half_open()
            if self._state is CircuitState.OPEN:
                raise CircuitBreakerOpen(self.name)

        try:
            result = await func()
        except Exception:
            await self._on_failure()
            raise
        else:
            await self._on_success()
            return result

    def _maybe_half_open(self) -> None:
        if (
            self._state is CircuitState.OPEN
            and self._clock() - self._opened_at >= self._recovery_seconds
        ):
            self._state = CircuitState.HALF_OPEN

    async def _on_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if (
                self._state is CircuitState.HALF_OPEN
                or self._failures >= self._failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
