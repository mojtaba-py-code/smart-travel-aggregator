"""Celery application and beat schedule.

Kept thin on purpose: tasks delegate to plain, unit-tested services. The broker
and result backend come from Redis (see settings). This module is intentionally
excluded from the coverage gate — its logic lives in the services it calls.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
_broker = str(settings.redis_url) if settings.redis_url else "memory://"

celery_app = Celery("smart_travel", broker=_broker, backend=_broker)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "monitor-prices-every-15-min": {
            "task": "app.workers.tasks.monitor_prices",
            "schedule": 900.0,
        },
        "cleanup-audit-log-daily": {
            "task": "app.workers.tasks.cleanup_audit_log",
            "schedule": 86400.0,
        },
    },
)
