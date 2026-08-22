"""Resolving the caller's address from X-Forwarded-For, safely."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from starlette.requests import Request

from app.container import Container
from app.core import middleware
from app.core.client_ip import ProxyTrust
from app.core.config import Settings
from app.main import create_app

TRUSTED = ["10.0.0.0/8"]


def _request(peer: str | None, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (peer, 51234) if peer is not None else None,
        }
    )


def test_forwarded_header_is_ignored_when_no_proxy_is_trusted() -> None:
    trust = ProxyTrust()
    assert trust.configured is False
    # Anyone can send this header; with no proxy in front of us it is a forgery.
    assert trust.client_ip(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_forwarded_header_is_ignored_from_an_untrusted_peer() -> None:
    trust = ProxyTrust(TRUSTED)
    assert trust.client_ip(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_forwarded_header_is_honoured_from_a_trusted_proxy() -> None:
    trust = ProxyTrust(TRUSTED)
    assert trust.client_ip(_request("10.1.2.3", "203.0.113.9")) == "203.0.113.9"


def test_hops_left_of_the_trusted_proxy_are_discarded() -> None:
    trust = ProxyTrust(TRUSTED)
    # "1.2.3.4" is whatever the caller chose to send; the proxy appended the
    # address it actually saw, which is the right-most untrusted hop.
    request = _request("10.1.2.3", "1.2.3.4, 203.0.113.9")
    assert trust.client_ip(request) == "203.0.113.9"


def test_chained_trusted_proxies_are_skipped() -> None:
    trust = ProxyTrust(TRUSTED)
    request = _request("10.1.2.3", "203.0.113.9, 10.4.5.6")
    assert trust.client_ip(request) == "203.0.113.9"


def test_trusted_proxy_without_a_header_falls_back_to_the_peer() -> None:
    trust = ProxyTrust(TRUSTED)
    assert trust.client_ip(_request("10.1.2.3")) == "10.1.2.3"
    assert trust.client_ip(_request("10.1.2.3", "   ")) == "10.1.2.3"


def test_garbage_in_the_header_is_not_trusted() -> None:
    trust = ProxyTrust(TRUSTED)
    assert trust.trusts("not-an-ip") is False


def test_invalid_cidr_is_dropped_rather_than_crashing_startup() -> None:
    trust = ProxyTrust(["10.0.0.0/8", "definitely-not-a-cidr"])
    assert trust.configured is True
    assert trust.trusts("10.0.0.1") is True


def test_missing_client_yields_no_address() -> None:
    assert ProxyTrust(TRUSTED).client_ip(_request(None)) is None


class _RecordingLogger:
    """Stands in for the access logger so the emitted fields can be inspected."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.events.append({"event": event, **fields})

    def error(self, event: str, **fields: Any) -> None:
        self.events.append({"event": event, **fields})


async def _log_one_request(settings: Settings) -> None:
    container = Container(settings)
    try:
        app = create_app(settings, container=container)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, client=("10.1.2.3", 51234))
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/health/live", headers={"X-Forwarded-For": "203.0.113.9"}
                )
                assert response.status_code == 200
    finally:
        await container.aclose()


async def test_access_log_records_the_caller_behind_a_trusted_proxy(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The access log is the one place the address is used for tracing."""
    recorder = _RecordingLogger()
    monkeypatch.setattr(middleware, "logger", recorder)

    await _log_one_request(settings.model_copy(update={"trusted_proxy_cidrs": TRUSTED}))

    completed = [e for e in recorder.events if e["event"] == "request_completed"]
    assert [e["client"] for e in completed] == ["203.0.113.9"]


async def test_access_log_keeps_the_peer_when_no_proxy_is_trusted(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _RecordingLogger()
    monkeypatch.setattr(middleware, "logger", recorder)

    await _log_one_request(settings)

    completed = [e for e in recorder.events if e["event"] == "request_completed"]
    assert [e["client"] for e in completed] == ["10.1.2.3"]
