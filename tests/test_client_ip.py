"""Resolving the caller's address from X-Forwarded-For, safely."""

from __future__ import annotations

from starlette.requests import Request

from app.core.client_ip import ProxyTrust

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
