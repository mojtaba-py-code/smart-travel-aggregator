"""Aggregate all v1 routers under a single APIRouter."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    currency,
    flights,
    health,
    hotels,
    price_alerts,
    weather,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(flights.router)
api_router.include_router(hotels.router)
api_router.include_router(weather.router)
api_router.include_router(currency.router)
api_router.include_router(price_alerts.router)
api_router.include_router(admin.router)
