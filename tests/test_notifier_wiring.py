"""Which notifier the container picks, and when."""

from __future__ import annotations

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
