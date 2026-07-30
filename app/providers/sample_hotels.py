"""Deterministic sample hotel provider.

Stands in for a paid inventory API (Amadeus Hotels, Hotelbeds, ...) behind the
:class:`HotelProvider` port, returning stable, plausible results derived from
the query so the aggregation and API layers can run without credentials.
"""

from __future__ import annotations

import hashlib
import random

from app.domain.dto import NormalizedHotel
from app.domain.money import Money
from app.domain.ports import HotelSearchQuery

_NAMES = ["Grand", "Central", "Riverside", "Park", "Royal", "Harbor", "Old Town", "Skyline"]
_KINDS = ["Hotel", "Suites", "Inn", "Residence", "Boutique"]
_AMENITIES = ["wifi", "breakfast", "parking", "pool", "gym", "spa", "airport_shuttle"]


class SampleHotelProvider:
    def __init__(self, name: str, *, base_price: int = 8000) -> None:
        self.name = name
        self._base_price = base_price

    async def search(self, query: HotelSearchQuery) -> list[NormalizedHotel]:
        rng = random.Random(self._seed(query))  # noqa: S311 - not for security
        hotels: list[NormalizedHotel] = []

        for index in range(rng.randint(4, 7)):
            rating = round(rng.uniform(3.0, 5.0), 1)
            per_night = int(self._base_price + rating * 1200 + rng.randint(0, 5000))
            per_night += (query.guests - 1) * rng.randint(500, 1500)
            amenities = rng.sample(_AMENITIES, rng.randint(2, 5))
            hotels.append(
                NormalizedHotel(
                    id=self._offer_id(query, index),
                    provider=self.name,
                    name=f"{rng.choice(_NAMES)} {rng.choice(_KINDS)}",
                    city=query.city,
                    rating=rating,
                    reviews_count=rng.randint(40, 4000),
                    price_per_night=Money(amount_minor=per_night, currency="USD"),
                    amenities=sorted(amenities),
                )
            )
        return hotels

    def _seed(self, query: HotelSearchQuery) -> int:
        raw = f"{self.name}:{query.city}:{query.check_in}:{query.check_out}:{query.guests}"
        return int(hashlib.sha256(raw.encode()).hexdigest(), 16) % (2**32)

    def _offer_id(self, query: HotelSearchQuery, index: int) -> str:
        raw = f"{self.name}:{query.city}:{query.check_in}:{index}"
        return "ho_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
