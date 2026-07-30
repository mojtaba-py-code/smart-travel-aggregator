"""Email verification, password reset and logout / token revocation."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.container import Container
from app.core.config import Settings
from app.core.security import create_reset_token, create_verify_token
from tests.conftest import VALID_PASSWORD, login, register_user


def _settings(app: FastAPI) -> Settings:
    container: Container = app.state.container
    return container.settings


async def test_register_sends_verification(client: httpx.AsyncClient, app: FastAPI) -> None:
    container: Container = app.state.container
    await register_user(client)
    sent = container.notifier.sent  # type: ignore[attr-defined]
    assert any("Verify" in subject for _to, subject, _body in sent)


async def test_verify_email_flow(client: httpx.AsyncClient, app: FastAPI) -> None:
    user = await register_user(client)
    token = create_verify_token(user["id"], _settings(app))

    resp = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 200

    tokens = await login(client)
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.json()["is_verified"] is True


async def test_verify_email_rejects_bad_token(client: httpx.AsyncClient) -> None:
    await register_user(client)
    resp = await client.post("/api/v1/auth/verify-email", json={"token": "garbage"})
    assert resp.status_code == 401


async def test_verify_email_rejects_wrong_token_type(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    user = await register_user(client)
    # A reset token must not be accepted by the verify endpoint.
    wrong = create_reset_token(user["id"], _settings(app))
    resp = await client.post("/api/v1/auth/verify-email", json={"token": wrong})
    assert resp.status_code == 401


async def test_resend_verification_does_not_leak_accounts(client: httpx.AsyncClient) -> None:
    # Unknown address still returns 200 with the same generic message.
    resp = await client.post(
        "/api/v1/auth/resend-verification", json={"email": "nobody@example.com"}
    )
    assert resp.status_code == 200


async def test_password_reset_request_is_silent_for_unknown_email(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "ghost@example.com"}
    )
    assert resp.status_code == 200


async def test_password_reset_full_flow(client: httpx.AsyncClient, app: FastAPI) -> None:
    user = await register_user(client)
    token = create_reset_token(user["id"], _settings(app))
    new_password = "BrandNewPw9!"

    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": new_password},
    )
    assert resp.status_code == 200

    # Old password no longer works; new one does.
    old = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": VALID_PASSWORD}
    )
    assert old.status_code == 401
    fresh = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": new_password}
    )
    assert fresh.status_code == 200


async def test_password_reset_rejects_weak_password(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    user = await register_user(client)
    token = create_reset_token(user["id"], _settings(app))
    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "weakpassword"},
    )
    assert resp.status_code == 422


async def test_logout_revokes_access_token(client: httpx.AsyncClient) -> None:
    await register_user(client)
    tokens = await login(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert logout.status_code == 200

    # The same access token is now rejected.
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_logout_revokes_refresh_token(client: httpx.AsyncClient) -> None:
    await register_user(client)
    tokens = await login(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


async def test_logout_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/logout", json={})
    assert resp.status_code == 401


@pytest.mark.parametrize("endpoint", ["verify-email", "password-reset/confirm"])
async def test_token_endpoints_reject_empty_token(
    client: httpx.AsyncClient, endpoint: str
) -> None:
    if endpoint == "verify-email":
        body = {"token": ""}
    else:
        body = {"token": "", "new_password": "Abc12345xy"}
    resp = await client.post(f"/api/v1/auth/{endpoint}", json=body)
    assert resp.status_code == 422
