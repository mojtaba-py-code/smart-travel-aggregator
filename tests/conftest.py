"""Shared test fixtures.

Each test gets an isolated on-disk SQLite database and a real ASGI client
wired to a purpose-built container, so tests exercise the full stack (routing,
middleware, DI, DB) without any external services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import update

from app.container import Container
from app.core.config import Settings
from app.db.base import Base
from app.db.models import User, UserRole
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "test.db"
    return Settings(
        environment="test",
        secret_key="test-secret-key-that-is-long-enough-1234",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        rate_limit_per_minute=10_000,
    )


@pytest_asyncio.fixture
async def container(settings: Settings) -> AsyncIterator[Container]:
    instance = Container(settings)
    async with instance.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield instance
    await instance.aclose()


@pytest.fixture
def app(container: Container) -> FastAPI:
    return create_app(container.settings, container=container)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client


VALID_PASSWORD = "Sup3rSecret!"


async def register_user(
    client: httpx.AsyncClient, email: str = "traveler@example.com"
) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": VALID_PASSWORD, "full_name": "Test Traveller"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def login(client: httpx.AsyncClient, email: str = "traveler@example.com") -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": VALID_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    await register_user(client)
    tokens = await login(client)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(client: httpx.AsyncClient, container: Container) -> dict[str, str]:
    await register_user(client, email="admin@example.com")
    async with container.session_factory() as session:
        await session.execute(
            update(User).where(User.email == "admin@example.com").values(role=UserRole.ADMIN)
        )
        await session.commit()
    tokens = await login(client, email="admin@example.com")
    return {"Authorization": f"Bearer {tokens['access_token']}"}
