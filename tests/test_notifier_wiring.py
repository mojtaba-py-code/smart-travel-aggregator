"""Which notifier the container picks, and how the SMTP one connects."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

import pytest

from app.container import Container
from app.core.config import Settings
from app.services.notifications import ConsoleNotifier, SmtpNotifier


async def test_console_notifier_when_no_smtp_host_is_configured(settings: Settings) -> None:
    container = Container(settings)
    try:
        assert isinstance(container.notifier, ConsoleNotifier)
    finally:
        await container.aclose()


async def test_smtp_notifier_is_wired_from_the_settings(settings: Settings) -> None:
    configured = settings.model_copy(
        update={
            "smtp_host": "smtp.example.com",
            "smtp_username": "postmaster@example.com",
        }
    )
    container = Container(configured)
    try:
        # Verification and reset mail is only real when this is the SMTP one.
        assert isinstance(container.notifier, SmtpNotifier)
    finally:
        await container.aclose()


async def test_smtp_login_happens_over_a_verified_tls_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SMTP password may only travel over a connection we actually verified."""
    captured: dict[str, Any] = {}

    class _FakeSMTP:
        def __init__(self, host: str, port: int) -> None:
            captured["host"] = host

        def __enter__(self) -> _FakeSMTP:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def starttls(self, *, context: ssl.SSLContext | None = None) -> None:
            captured["context"] = context

        def login(self, username: str, password: str) -> None:
            captured["login"] = username

        def send_message(self, message: EmailMessage) -> None:
            captured["to"] = message["To"]

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    notifier = SmtpNotifier(
        host="smtp.example.com",
        port=587,
        username="postmaster@example.com",
        password="s3cret",
        sender="no-reply@example.com",
    )

    await notifier.send(to="traveler@example.com", subject="Verify", body="link")

    assert captured["to"] == "traveler@example.com"
    assert captured["login"] == "postmaster@example.com"
    context = captured["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode is ssl.CERT_REQUIRED
