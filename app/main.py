"""Application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.container import Container
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.metrics import PrometheusMiddleware, metrics_endpoint
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware

logger = get_logger("app")


def create_app(settings: Settings | None = None, *, container: Container | None = None) -> FastAPI:
    settings = settings or (container.settings if container else get_settings())
    configure_logging(json_logs=settings.is_production, level="DEBUG" if settings.debug else "INFO")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # A caller-supplied container (tests) is owned by the caller; otherwise we
        # build one for the lifetime of the app and dispose of it on shutdown.
        owned = container is None
        active = container or Container(settings)
        app.state.container = active
        logger.info("app_started", environment=settings.environment, version=__version__)
        try:
            yield
        finally:
            if owned:
                await active.aclose()
            logger.info("app_stopped")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Aggregates flights, hotels, weather and currency behind one resilient API.",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    app.add_api_route("/metrics", metrics_endpoint, include_in_schema=False)
    return app


app = create_app()
