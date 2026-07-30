"""Price-alert CRUD, ownership and access control."""

from __future__ import annotations

import httpx

from tests.conftest import login, register_user

ALERT = {
    "origin": "THR",
    "destination": "IST",
    "departure_date": "2026-08-10",
    "target_amount_minor": 10000,
    "currency": "USD",
    "channel": "email",
}


async def test_create_and_list_alert(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post("/api/v1/price-alerts", json=ALERT, headers=auth_headers)
    assert created.status_code == 201
    alert_id = created.json()["id"]

    listing = await client.get("/api/v1/price-alerts", headers=auth_headers)
    assert listing.status_code == 200
    assert any(a["id"] == alert_id for a in listing.json())


async def test_create_alert_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/price-alerts", json=ALERT)
    assert resp.status_code == 401


async def test_create_alert_same_route_rejected(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {**ALERT, "destination": "THR"}
    resp = await client.post("/api/v1/price-alerts", json=payload, headers=auth_headers)
    assert resp.status_code == 400


async def test_delete_alert(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post("/api/v1/price-alerts", json=ALERT, headers=auth_headers)
    alert_id = created.json()["id"]
    deleted = await client.delete(f"/api/v1/price-alerts/{alert_id}", headers=auth_headers)
    assert deleted.status_code == 204

    listing = await client.get("/api/v1/price-alerts", headers=auth_headers)
    assert all(a["id"] != alert_id for a in listing.json())


async def test_cannot_delete_another_users_alert(client: httpx.AsyncClient) -> None:
    await register_user(client, email="owner@example.com")
    owner_tokens = await login(client, email="owner@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_tokens['access_token']}"}
    created = await client.post("/api/v1/price-alerts", json=ALERT, headers=owner_headers)
    alert_id = created.json()["id"]

    await register_user(client, email="attacker@example.com")
    attacker_tokens = await login(client, email="attacker@example.com")
    attacker_headers = {"Authorization": f"Bearer {attacker_tokens['access_token']}"}

    resp = await client.delete(f"/api/v1/price-alerts/{alert_id}", headers=attacker_headers)
    assert resp.status_code == 404  # not leaked as 403


async def test_delete_missing_alert_returns_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.delete(
        "/api/v1/price-alerts/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert resp.status_code == 404
