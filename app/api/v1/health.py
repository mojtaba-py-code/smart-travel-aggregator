"""Liveness and readiness probes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app import __version__
from app.api.deps import get_container
from app.container import Container
from app.core.errors import ProviderUnavailableError
from app.schemas.common import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthOut)
async def live() -> HealthOut:
    return HealthOut(status="alive", version=__version__)


@router.get("/health/ready", response_model=HealthOut)
async def ready(container: Annotated[Container, Depends(get_container)]) -> HealthOut:
    try:
        async with container.session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised via dependency override
        raise ProviderUnavailableError("database is not reachable") from exc
    return HealthOut(status="ready", version=__version__)
