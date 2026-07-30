"""Canonical, provider-agnostic data transfer objects.

Every provider adapter maps its raw payload into one of these normalized
shapes, so the rest of the application never sees vendor-specific fields.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.money import Money

CabinClass = str


class NormalizedFlight(BaseModel):
    id: str
    provider: str
    airline: str
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int = Field(gt=0)
    stops: int = Field(ge=0)
    cabin_class: CabinClass
    price: Money

    @property
    def is_direct(self) -> bool:
        return self.stops == 0


class NormalizedHotel(BaseModel):
    id: str
    provider: str
    name: str
    city: str
    rating: float = Field(ge=0, le=5)
    reviews_count: int = Field(ge=0)
    price_per_night: Money
    amenities: list[str] = Field(default_factory=list)


class WeatherForecast(BaseModel):
    latitude: float
    longitude: float
    date: str
    temperature_c: float
    precipitation_probability: int = Field(ge=0, le=100)
    wind_kph: float = Field(ge=0)
    humidity: int = Field(ge=0, le=100)


class CurrencyConversion(BaseModel):
    base: str
    quote: str
    rate: float = Field(gt=0)
    amount: float
    converted: float
    as_of: str
