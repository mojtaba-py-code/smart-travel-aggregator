"""Auth endpoints and input validation."""

from __future__ import annotations

import httpx

from tests.conftest import VALID_PASSWORD, login, register_user


async def test_register_login_me_flow(client: httpx.AsyncClient) -> None:
    user = await register_user(client)
    assert user["email"] == "traveler@example.com"
    assert "id" in user

    tokens = await login(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "traveler@example.com"


async def test_duplicate_email_is_conflict(client: httpx.AsyncClient) -> None:
    await register_user(client)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "traveler@example.com", "password": VALID_PASSWORD},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "conflict"
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_weak_password_is_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "alllowercase"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


async def test_invalid_email_is_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": VALID_PASSWORD},
    )
    assert resp.status_code == 422


async def test_login_with_wrong_password_fails(client: httpx.AsyncClient) -> None:
    await register_user(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "traveler@example.com", "password": "WrongPass123"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


async def test_login_unknown_user_fails(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": VALID_PASSWORD},
    )
    assert resp.status_code == 401


async def test_refresh_issues_new_tokens(client: httpx.AsyncClient) -> None:
    await register_user(client)
    tokens = await login(client)
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_refresh_rejects_access_token(client: httpx.AsyncClient) -> None:
    await register_user(client)
    tokens = await login(client)
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert resp.status_code == 401


async def test_me_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_rejects_garbage_token(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert resp.status_code == 401
