"""Structured logging.

Every log line is a JSON object in production (easy to ship to Loki/ELK) and a
coloured console line in development. A contextvar carries the request id so it
is stamped on every line emitted while handling a request, without threading it
through every call.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import cast

import structlog
from structlog.typing import EventDict, WrappedLogger

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def _add_request_id(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    request_id = request_id_ctx.get()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging(*, json_logs: bool, level: str = "INFO") -> None:
    """Configure structlog + stdlib logging once, at application start-up."""
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_request_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy, ...) through the same handler.
    handler = logging.StreamHandler(sys.stdout)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))
