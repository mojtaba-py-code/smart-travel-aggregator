"""Prometheus metrics.

Exposes the RED signals (Rate, Errors, Duration) per route so the API can be
scraped by Prometheus and graphed in Grafana. Labels use the route *template*
(e.g. ``/flights/{id}``) rather than the concrete path, to keep cardinality
bounded.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    labelnames=("method", "path", "status"),
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "path"),
)

_METRICS_PATH = "/metrics"


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == _METRICS_PATH:
            return await call_next(request)

        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started

        # The matched route is only known after routing has run.
        template = _route_template(request)
        REQUEST_LATENCY.labels(request.method, template).observe(elapsed)
        REQUEST_COUNT.labels(request.method, template, response.status_code).inc()
        return response


def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
