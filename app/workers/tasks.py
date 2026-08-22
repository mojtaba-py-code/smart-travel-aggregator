"""Celery tasks — thin adapters around unit-tested services."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete

from app.container import Container
from app.core.config import get_settings
from app.db.models import AuditLog
from app.repositories.price_alerts import PriceAlertRepository
from app.repositories.users import UserRepository
from app.services.price_monitor import PriceMonitor
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.monitor_prices")
def monitor_prices() -> int:
    return asyncio.run(_monitor_prices())


async def _monitor_prices() -> int:
    container = Container(get_settings())
    try:
        async with container.session_factory() as session:
            monitor = PriceMonitor(
                alerts=PriceAlertRepository(session),
                users=UserRepository(session),
                flights=container.flight_service,
                notifier=container.notifier,
            )
            report = await monitor.run_once()
            await session.commit()
            return report.triggered
    finally:
        await container.aclose()


@celery_app.task(name="app.workers.tasks.cleanup_audit_log")
def cleanup_audit_log(retention_days: int = 90) -> int:
    return asyncio.run(_cleanup_audit_log(retention_days))


async def _cleanup_audit_log(retention_days: int) -> int:
    container = Container(get_settings())
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    try:
        async with container.session_factory() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(delete(AuditLog).where(AuditLog.created_at < cutoff)),
            )
            await session.commit()
            return result.rowcount or 0
    finally:
        await container.aclose()
