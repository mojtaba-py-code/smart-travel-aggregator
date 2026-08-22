"""Notification channels.

Business code depends on the :class:`Notifier` protocol. The container picks the
implementation: the SMTP notifier when ``SMTP_HOST`` is configured, otherwise the
console notifier, which logs the message instead of delivering it.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.logging import get_logger

logger = get_logger("notifications")


class Notifier(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleNotifier:
    """Logs the notification instead of sending it. Safe for dev and tests."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))
        logger.info("notification_sent", channel="console", to=to, subject=subject)


class SmtpNotifier:
    def __init__(self, *, host: str, port: int, username: str, password: str, sender: str) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender

    async def send(self, *, to: str, subject: str, body: str) -> None:  # pragma: no cover
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        # smtplib is blocking; in production this runs inside a Celery worker.
        with smtplib.SMTP(self._host, self._port) as server:
            server.starttls()
            server.login(self._username, self._password)
            server.send_message(message)
        logger.info("notification_sent", channel="smtp", to=to, subject=subject)
