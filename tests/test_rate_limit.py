"""Rate limiting at the unit and HTTP level."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from app.container import Container
from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.db.base import Base
from app.main import create_app


async def test_rate_limiter_blocks_after_limit() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    assert (await limiter.check("ip"))[0] is True
    assert (await limiter.check("ip"))[0] is True
    allowed, remaining = await limiter.check("ip")
    assert allowed is False
    assert remaining == 0
    # a different identity is tracked independently
    assert (await limiter.check("other"))[0] is True


@pytest_asyncio.fixture
async def throttled_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        environment="test",
        secret_key="throttle-secret-key-long-enough-00000000",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'rl.db'}",
        rate_limit_per_minute=2,
    )
    container = Container(settings)
    async with container.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = create_app(settings, container=container)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    await container.aclose()


async def test_http_rate_limit_returns_429(throttled_client: httpx.AsyncClient) -> None:
    params = {"origin": "THR", "destination": "IST", "departure_date": "2026-08-10"}
    assert (await throttled_client.get("/api/v1/flights/search", params=params)).status_code == 200
    assert (await throttled_client.get("/api/v1/flights/search", params=params)).status_code == 200
    blocked = await throttled_client.get("/api/v1/flights/search", params=params)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limited"


@pytest.mark.parametrize("identity", ["a", "b", "c"])
async def test_rate_limiter_remaining_counts_down(identity: str) -> None:
    limiter = RateLimiter(limit=3)
    _, remaining = await limiter.check(identity)
    assert remaining == 2
