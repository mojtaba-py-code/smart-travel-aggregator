"""Price monitoring service."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.container import Container
from app.db.models import AlertChannel
from app.domain.dto import NormalizedFlight
from app.domain.money import Money
from app.domain.ports import FlightSearchQuery
from app.repositories.price_alerts import PriceAlertRepository
from app.repositories.users import UserRepository
from app.services.aggregation import FlightAggregationService
from app.services.notifications import ConsoleNotifier
from app.services.price_monitor import PriceMonitor


class FixedPriceProvider:
    name = "fixed"

    def __init__(self, price_minor: int) -> None:
        self._price = price_minor

    async def search(self, query: FlightSearchQuery) -> list[NormalizedFlight]:
        departure = datetime.combine(query.departure_date, datetime.min.time(), UTC)
        return [
            NormalizedFlight(
                id="fixed-1",
                provider=self.name,
                airline="TestAir",
                origin=query.origin,
                destination=query.destination,
                departure_time=departure,
                arrival_time=departure,
                duration_minutes=120,
                stops=0,
                cabin_class="economy",
                price=Money(amount_minor=self._price, currency="USD"),
            )
        ]


async def _seed_user_and_alert(container: Container, *, target: int) -> None:
    async with container.session_factory() as session:
        user = await UserRepository(session).create(
            email="watcher@example.com", hashed_password="x", full_name=None
        )
        await PriceAlertRepository(session).create(
            user_id=user.id,
            origin="THR",
            destination="IST",
            departure_date=date(2026, 8, 10).isoformat(),
            target_amount_minor=target,
            currency="USD",
            channel=AlertChannel.EMAIL,
        )
        await session.commit()


async def _run(container: Container, provider_price: int, notifier: ConsoleNotifier):  # type: ignore[no-untyped-def]
    flights = FlightAggregationService([FixedPriceProvider(provider_price)])
    async with container.session_factory() as session:
        monitor = PriceMonitor(
            alerts=PriceAlertRepository(session),
            users=UserRepository(session),
            flights=flights,
            notifier=notifier,
        )
        report = await monitor.run_once()
        await session.commit()
    return report


async def test_alert_triggers_when_price_below_target(container: Container) -> None:
    await _seed_user_and_alert(container, target=20000)
    notifier = ConsoleNotifier()
    report = await _run(container, 15000, notifier)

    assert report.checked == 1
    assert report.triggered == 1
    assert len(notifier.sent) == 1
    assert notifier.sent[0][0] == "watcher@example.com"


async def test_alert_does_not_trigger_when_price_above_target(container: Container) -> None:
    await _seed_user_and_alert(container, target=5000)
    notifier = ConsoleNotifier()
    report = await _run(container, 15000, notifier)

    assert report.triggered == 0
    assert notifier.sent == []


async def test_alert_is_deactivated_after_trigger(container: Container) -> None:
    await _seed_user_and_alert(container, target=20000)
    await _run(container, 15000, ConsoleNotifier())

    async with container.session_factory() as session:
        active = await PriceAlertRepository(session).list_active()
    assert active == []
