"""Provider ports (interfaces).

Business logic depends only on these protocols. Concrete adapters in
``app.providers`` implement them; new providers are added without touching any
caller (Open/Closed principle).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.domain.dto import (
    CurrencyConversion,
    NormalizedFlight,
    NormalizedHotel,
    WeatherForecast,
)


@dataclass(frozen=True, slots=True)
class FlightSearchQuery:
    origin: str
    destination: str
    departure_date: date
    adults: int = 1
    cabin_class: str = "economy"


@dataclass(frozen=True, slots=True)
class HotelSearchQuery:
    city: str
    check_in: date
    check_out: date
    guests: int = 2

    @property
    def nights(self) -> int:
        return max(1, (self.check_out - self.check_in).days)


class FlightProvider(Protocol):
    name: str

    async def search(self, query: FlightSearchQuery) -> list[NormalizedFlight]: ...


class HotelProvider(Protocol):
    name: str

    async def search(self, query: HotelSearchQuery) -> list[NormalizedHotel]: ...


class WeatherProvider(Protocol):
    name: str

    async def forecast(self, latitude: float, longitude: float, day: date) -> WeatherForecast: ...


class CurrencyProvider(Protocol):
    name: str

    async def convert(self, base: str, quote: str, amount: float) -> CurrencyConversion: ...
