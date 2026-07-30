"""Circuit breaker, cache and resilient HTTP client."""

from __future__ import annotations

import httpx
import pytest

from app.core.errors import ProviderUnavailableError
from app.providers.http_client import ResilientHttpClient
from app.resilience.cache import InMemoryCache, RedisCache
from app.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_cache_expires() -> None:
    cache = InMemoryCache()
    await cache.set("k", "v", ttl=100)
    assert await cache.get("k") == "v"
    await cache.set("gone", "v", ttl=0)
    assert await cache.get("gone") is None
    await cache.delete("k")
    assert await cache.get("k") is None
    await cache.set("x", "y", ttl=100)
    await cache.clear()
    assert await cache.get("x") is None


class FakeRedis:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._data[key] = value.encode()

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)


async def test_redis_cache_round_trip() -> None:
    cache = RedisCache(FakeRedis())  # type: ignore[arg-type]
    assert await cache.get("missing") is None
    await cache.set("k", "value", ttl=60)
    assert await cache.get("k") == "value"
    await cache.delete("k")
    assert await cache.get("k") is None


async def test_circuit_breaker_opens_after_threshold() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("x", failure_threshold=2, recovery_seconds=10, clock=clock)

    async def boom() -> None:
        raise RuntimeError("down")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpen):
        await breaker.call(boom)


async def test_circuit_breaker_recovers() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("x", failure_threshold=1, recovery_seconds=5, clock=clock)

    async def boom() -> None:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN

    clock.now = 6.0  # past the recovery window -> half-open probe allowed

    async def ok() -> str:
        return "recovered"

    assert await breaker.call(ok) == "recovered"
    assert breaker.state is CircuitState.CLOSED


async def test_http_client_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as raw:
        client = ResilientHttpClient(raw, provider="test", max_retries=3, backoff_base=0.0)
        result = await client.get_json("http://svc/data")
    assert result == {"ok": True}
    assert calls["n"] == 3


async def test_http_client_gives_up_and_raises() -> None:
    transport = httpx.MockTransport(lambda _req: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as raw:
        client = ResilientHttpClient(raw, provider="test", max_retries=1, backoff_base=0.0)
        with pytest.raises(ProviderUnavailableError):
            await client.get_json("http://svc/data")


async def test_http_client_uses_cache() -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"value": calls["n"]})

    transport = httpx.MockTransport(handler)
    cache = InMemoryCache()
    async with httpx.AsyncClient(transport=transport) as raw:
        client = ResilientHttpClient(raw, provider="test", cache=cache, backoff_base=0.0)
        first = await client.get_json("http://svc/data", cache_ttl=60)
        second = await client.get_json("http://svc/data", cache_ttl=60)
    assert first == second
    assert calls["n"] == 1  # second call served from cache
