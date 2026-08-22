"""Rate limiting at the unit and HTTP level."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from app.container import Container
from app.core.config import Settings
from app.core.rate_limit import InMemoryRateLimiter, RedisRateLimiter
from app.db.base import Base
from app.main import create_app


async def test_rate_limiter_blocks_after_limit() -> None:
    limiter = InMemoryRateLimiter(limit=2, window_seconds=60)
    assert (await limiter.check("ip"))[0] is True
    assert (await limiter.check("ip"))[0] is True
    allowed, remaining = await limiter.check("ip")
    assert allowed is False
    assert remaining == 0
    # a different identity is tracked independently
    assert (await limiter.check("other"))[0] is True


SEARCH = {"origin": "THR", "destination": "IST", "departure_date": "2026-08-10"}


def _throttled_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        environment="test",
        secret_key="throttle-secret-key-long-enough-00000000",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'rl.db'}",
        rate_limit_per_minute=2,
        **overrides,
    )


async def _serve(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    container = Container(settings)
    async with container.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = create_app(settings, container=container)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    await container.aclose()


@pytest_asyncio.fixture
async def throttled_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async for client in _serve(_throttled_settings(tmp_path)):
        yield client


@pytest_asyncio.fixture
async def proxied_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    # The ASGI transport presents 127.0.0.1 as the peer, so this makes the test
    # client look like a request arriving through a proxy we operate.
    async for client in _serve(_throttled_settings(tmp_path, trusted_proxy_cidrs="127.0.0.0/8")):
        yield client


async def test_http_rate_limit_returns_429(throttled_client: httpx.AsyncClient) -> None:
    assert (await throttled_client.get("/api/v1/flights/search", params=SEARCH)).status_code == 200
    assert (await throttled_client.get("/api/v1/flights/search", params=SEARCH)).status_code == 200
    blocked = await throttled_client.get("/api/v1/flights/search", params=SEARCH)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limited"


async def test_spoofed_forwarded_header_does_not_buy_a_fresh_bucket(
    throttled_client: httpx.AsyncClient,
) -> None:
    # No trusted proxy is configured, so X-Forwarded-For is caller-controlled
    # noise: a new value per request must not reset the counter.
    for spoof in ("1.1.1.1", "2.2.2.2"):
        resp = await throttled_client.get(
            "/api/v1/flights/search", params=SEARCH, headers={"X-Forwarded-For": spoof}
        )
        assert resp.status_code == 200
    blocked = await throttled_client.get(
        "/api/v1/flights/search", params=SEARCH, headers={"X-Forwarded-For": "3.3.3.3"}
    )
    assert blocked.status_code == 429


async def test_callers_behind_a_trusted_proxy_get_their_own_bucket(
    proxied_client: httpx.AsyncClient,
) -> None:
    first = {"X-Forwarded-For": "203.0.113.9"}
    second = {"X-Forwarded-For": "198.51.100.7"}
    for _ in range(2):
        resp = await proxied_client.get("/api/v1/flights/search", params=SEARCH, headers=first)
        assert resp.status_code == 200
    # One client exhausting its quota must not lock out everybody else.
    assert (
        await proxied_client.get("/api/v1/flights/search", params=SEARCH, headers=second)
    ).status_code == 200
    assert (
        await proxied_client.get("/api/v1/flights/search", params=SEARCH, headers=first)
    ).status_code == 429


@pytest.mark.parametrize("identity", ["a", "b", "c"])
async def test_rate_limiter_remaining_counts_down(identity: str) -> None:
    limiter = InMemoryRateLimiter(limit=3)
    _, remaining = await limiter.check(identity)
    assert remaining == 2


class FakeRedisCounter:
    """Minimal INCR/EXPIRE stand-in for the Redis rate limiter."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.expires[key] = seconds


async def test_redis_rate_limiter_blocks_after_limit() -> None:
    limiter = RedisRateLimiter(FakeRedisCounter(), limit=2, window_seconds=30)  # type: ignore[arg-type]
    assert await limiter.check("ip") == (True, 1)
    assert await limiter.check("ip") == (True, 0)
    allowed, remaining = await limiter.check("ip")
    assert allowed is False
    assert remaining == 0
