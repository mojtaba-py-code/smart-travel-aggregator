"""Work out who is really calling when the app sits behind a reverse proxy.

Behind Render, Nginx or any load balancer every request arrives from the proxy,
so a bare ``request.client.host`` collapses the per-client rate limiter into one
global bucket — a single noisy caller then throttles everybody — and writes the
proxy's address into the audit log instead of the caller's.

``X-Forwarded-For`` answers the question, but it is client-supplied: anyone can
send one. It is therefore honoured only when the immediate peer is inside an
operator-configured trusted network, and only the right-most hop that we did not
put there is taken. The tail of the header is what our own proxies appended;
everything to the left of it may have been forged by the caller.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence

from starlette.requests import Request

from app.core.logging import get_logger

logger = get_logger("client_ip")

FORWARDED_FOR_HEADER = "x-forwarded-for"


class ProxyTrust:
    """Resolves the caller's address given the networks we trust to forward."""

    def __init__(self, trusted_cidrs: Sequence[str] | None = None) -> None:
        self._networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for cidr in trusted_cidrs or []:
            try:
                self._networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                logger.warning("ignoring_invalid_trusted_proxy_cidr", cidr=cidr)

    @property
    def configured(self) -> bool:
        return bool(self._networks)

    def trusts(self, address: str | None) -> bool:
        if not address or not self._networks:
            return False
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        return any(ip in network for network in self._networks)

    def client_ip(self, request: Request) -> str | None:
        """The caller's address, or ``None`` when it cannot be determined."""
        peer = request.client.host if request.client else None
        # No trusted proxy in front of us: the header is pure caller input.
        if not self.trusts(peer):
            return peer
        forwarded = request.headers.get(FORWARDED_FOR_HEADER, "")
        hops = [part.strip() for part in forwarded.split(",") if part.strip()]
        for hop in reversed(hops):
            if not self.trusts(hop):
                return hop
        return peer
