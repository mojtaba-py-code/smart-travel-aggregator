"""Prometheus metrics endpoint."""

from __future__ import annotations

import httpx


async def test_metrics_endpoint_exposes_prometheus(client: httpx.AsyncClient) -> None:
    # Generate some traffic so counters have something to report.
    await client.get("/api/v1/health/live")

    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


async def test_metrics_records_route_template(client: httpx.AsyncClient) -> None:
    await client.get("/api/v1/health/live")
    resp = await client.get("/metrics")
    # The label uses the matched route template (parameterised routes collapse to
    # e.g. /price-alerts/{alert_id}), keeping label cardinality bounded.
    assert 'path="/health/live"' in resp.text
