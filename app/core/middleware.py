"""HTTP middleware: correlation ids, access logging and hardened headers."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.client_ip import ProxyTrust
from app.core.logging import get_logger, request_id_ctx

logger = get_logger("http")

REQUEST_ID_HEADER = "X-Request-ID"

# Used until the container is on ``app.state``: trusting nothing means the
# access log falls back to the immediate peer, which is what it logged before.
_NO_TRUSTED_PROXY = ProxyTrust()


def _client_ip(request: Request) -> str | None:
    """Resolve the caller the same way the limiter and the audit log do.

    Behind a proxy the peer address is the proxy's, so tracing a request back to
    whoever made it needs the operator's trusted networks from the container.
    """
    container = getattr(request.app.state, "container", None)
    trust: ProxyTrust = _NO_TRUSTED_PROXY if container is None else container.proxy_trust
    return trust.client_ip(request)


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a request id and emit a structured access log per request."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming or uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers build the response; we only log timing here.
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=elapsed_ms,
            )
            raise
        finally:
            request_id_ctx.reset(token)

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=elapsed_ms,
            client=_client_ip(request),
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach a conservative set of security headers to every response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response
