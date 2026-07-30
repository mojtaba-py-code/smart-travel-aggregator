"""Price monitoring use-case.

Checks every active price alert against the cheapest currently-available fare
and notifies the owner when the target price is met. Designed to be driven by a
Celery beat schedule, but pure enough to unit-test without any broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.core.logging import get_logger
from app.db.models import PriceAlert, User
from app.domain.ports import FlightSearchQuery
from app.repositories.price_alerts import PriceAlertRepository
from app.repositories.users import UserRepository
from app.services.aggregation import FlightAggregationService, SortKey
from app.services.notifications import Notifier

logger = get_logger("price_monitor")


@dataclass(frozen=True, slots=True)
class MonitorReport:
    checked: int
    triggered: int


class PriceMonitor:
    def __init__(
        self,
        *,
        alerts: PriceAlertRepository,
        users: UserRepository,
        flights: FlightAggregationService,
        notifier: Notifier,
    ) -> None:
        self._alerts = alerts
        self._users = users
        self._flights = flights
        self._notifier = notifier

    async def run_once(self) -> MonitorReport:
        active = await self._alerts.list_active()
        triggered = 0
        for alert in active:
            if await self._check(alert):
                triggered += 1
        logger.info("price_monitor_run", checked=len(active), triggered=triggered)
        return MonitorReport(checked=len(active), triggered=triggered)

    async def _check(self, alert: PriceAlert) -> bool:
        cheapest = await self._cheapest_price(alert)
        if cheapest is None or cheapest > alert.target_amount_minor:
            return False

        user = await self._users.get_by_id(alert.user_id)
        if user is not None:
            await self._notify(user, alert, cheapest)

        alert.is_active = False
        alert.triggered_at = datetime.now(UTC)
        return True

    async def _cheapest_price(self, alert: PriceAlert) -> int | None:
        try:
            departure = date.fromisoformat(alert.departure_date)
        except ValueError:
            logger.warning("alert_bad_date", alert_id=str(alert.id))
            return None

        query = FlightSearchQuery(
            origin=alert.origin, destination=alert.destination, departure_date=departure
        )
        result = await self._flights.search(query, sort=SortKey.PRICE, limit=1)
        if not result.items:
            return None
        return result.items[0].flight.price.amount_minor

    async def _notify(self, user: User, alert: PriceAlert, price_minor: int) -> None:
        subject = f"Price drop: {alert.origin} to {alert.destination}"
        body = (
            f"A fare of {price_minor / 100:.2f} {alert.currency} is now available "
            f"for {alert.origin}-{alert.destination} on {alert.departure_date}, "
            f"below your target of {alert.target_amount_minor / 100:.2f} {alert.currency}."
        )
        await self._notifier.send(to=user.email, subject=subject, body=body)
