"""Admin RBAC, health probes and generic error shape."""

from __future__ import annotations

import httpx


async def test_live_probe(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


async def test_ready_probe(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


async def test_admin_metrics_requires_admin(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/admin/metrics", headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


async def test_admin_metrics_for_admin(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    # Generate some activity first.
    await client.get(
        "/api/v1/flights/search",
        params={"origin": "THR", "destination": "IST", "departure_date": "2026-08-10"},
        headers=admin_headers,
    )
    resp = await client.get("/api/v1/admin/metrics", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_users"] >= 1
    assert "popular_routes" in body


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["code"] == "http_error"


async def test_security_headers_present(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "X-Request-ID" in resp.headers
