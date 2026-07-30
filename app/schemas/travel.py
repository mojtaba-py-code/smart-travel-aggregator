"""Response schemas for the travel endpoints (flights, weather, currency)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import MoneyOut, PageInfo


class FlightOfferOut(BaseModel):
    id: str
    airline: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    stops: int
    cabin_class: str
    price: MoneyOut
    provider: str
    score: float


class SearchMetaOut(BaseModel):
    degraded: bool
    providers_ok: int
    providers_failed: int
    total: int


class FlightSearchResponse(BaseModel):
    data: list[FlightOfferOut]
    page: PageInfo
    meta: SearchMetaOut


class WeatherOut(BaseModel):
    latitude: float
    longitude: float
    date: str
    temperature_c: float
    precipitation_probability: int
    wind_kph: float
    humidity: int


class CurrencyOut(BaseModel):
    base: str
    quote: str
    rate: float
    amount: float
    converted: float
    as_of: str


class PriceAlertCreate(BaseModel):
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    departure_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    target_amount_minor: int = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    channel: str = Field(default="email", pattern=r"^(email|push)$")


class PriceAlertOut(BaseModel):
    id: uuid.UUID
    origin: str
    destination: str
    departure_date: str
    target_amount_minor: int
    currency: str
    channel: str
    is_active: bool
    created_at: datetime
