"""Deterministic sample flight provider.

Real flight inventory lives behind paid APIs (Amadeus, Sabre, ...). This
adapter implements the same :class:`FlightProvider` port and returns stable,
plausible results derived from the query, so the aggregation, ranking and API
layers can be exercised end-to-end without external credentials. Swapping in a
real provider is a one-line registry change.
"""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, time, timedelta

from app.domain.dto import NormalizedFlight
from app.domain.money import Money
from app.domain.ports import FlightSearchQuery

_CABIN_MULTIPLIER = {"economy": 1.0, "premium": 1.6, "business": 2.8, "first": 4.5}


class SampleFlightProvider:
    def __init__(self, name: str, airlines: list[str], *, base_price: int = 12000) -> None:
        self.name = name
        self._airlines = airlines
        self._base_price = base_price

    async def search(self, query: FlightSearchQuery) -> list[NormalizedFlight]:
        rng = random.Random(self._seed(query))  # noqa: S311 - not for security
        cabin_factor = _CABIN_MULTIPLIER.get(query.cabin_class, 1.0)
        flights: list[NormalizedFlight] = []

        for index in range(rng.randint(3, 6)):
            airline = rng.choice(self._airlines)
            stops = rng.choices([0, 1, 2], weights=[6, 3, 1])[0]
            depart_hour = rng.randint(5, 21)
            duration = rng.randint(90, 240) + stops * rng.randint(45, 120)
            minute = rng.choice([0, 15, 30, 45])
            departure = datetime.combine(
                query.departure_date, time(hour=depart_hour, minute=minute), UTC
            )
            arrival = departure + timedelta(minutes=duration)
            price_minor = int((self._base_price + duration * 20 + stops * 1500) * cabin_factor)
            price_minor += rng.randint(0, 4000) * query.adults

            flights.append(
                NormalizedFlight(
                    id=self._offer_id(query, index),
                    provider=self.name,
                    airline=airline,
                    origin=query.origin,
                    destination=query.destination,
                    departure_time=departure,
                    arrival_time=arrival,
                    duration_minutes=duration,
                    stops=stops,
                    cabin_class=query.cabin_class,
                    price=Money(amount_minor=price_minor, currency="USD"),
                )
            )
        return flights

    def _seed(self, query: FlightSearchQuery) -> int:
        raw = (
            f"{self.name}:{query.origin}:{query.destination}"
            f":{query.departure_date}:{query.cabin_class}"
        )
        return int(hashlib.sha256(raw.encode()).hexdigest(), 16) % (2**32)

    def _offer_id(self, query: FlightSearchQuery, index: int) -> str:
        raw = f"{self.name}:{query.origin}{query.destination}:{query.departure_date}:{index}"
        return "fl_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
