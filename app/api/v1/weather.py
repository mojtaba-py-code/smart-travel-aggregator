"""Weather forecast endpoint."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import enforce_rate_limit, get_weather_provider
from app.domain.ports import WeatherProvider
from app.schemas.travel import WeatherOut

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("", response_model=WeatherOut, dependencies=[Depends(enforce_rate_limit)])
async def get_weather(
    provider: Annotated[WeatherProvider, Depends(get_weather_provider)],
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    day: Annotated[date, Query(description="Forecast date (YYYY-MM-DD)")],
) -> WeatherOut:
    forecast = await provider.forecast(latitude, longitude, day)
    return WeatherOut(**forecast.model_dump())
