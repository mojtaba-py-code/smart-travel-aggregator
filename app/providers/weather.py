"""Open-Meteo weather adapter (free, no API key required)."""

from __future__ import annotations

from datetime import date
from statistics import fmean
from typing import Any

from app.core.errors import ProviderUnavailableError
from app.domain.dto import WeatherForecast
from app.providers.http_client import ResilientHttpClient


class OpenMeteoWeatherProvider:
    name = "open-meteo"

    def __init__(self, http: ResilientHttpClient, *, base_url: str, cache_ttl: int) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._cache_ttl = cache_ttl

    async def forecast(self, latitude: float, longitude: float, day: date) -> WeatherForecast:
        iso_day = day.isoformat()
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "temperature_2m_max,precipitation_probability_max,wind_speed_10m_max",
            "hourly": "relative_humidity_2m",
            "start_date": iso_day,
            "end_date": iso_day,
            "timezone": "UTC",
        }
        payload = await self._http.get_json(
            f"{self._base_url}/forecast", params=params, cache_ttl=self._cache_ttl
        )
        return self._normalize(payload, latitude, longitude, iso_day)

    def _normalize(
        self, payload: Any, latitude: float, longitude: float, iso_day: str
    ) -> WeatherForecast:
        try:
            daily = payload["daily"]
            temperature = float(daily["temperature_2m_max"][0])
            precipitation = int(daily["precipitation_probability_max"][0] or 0)
            wind = float(daily["wind_speed_10m_max"][0])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderUnavailableError("open-meteo returned an unexpected payload") from exc

        humidity = self._mean_humidity(payload, iso_day)
        return WeatherForecast(
            latitude=latitude,
            longitude=longitude,
            date=iso_day,
            temperature_c=round(temperature, 1),
            precipitation_probability=max(0, min(100, precipitation)),
            wind_kph=round(wind, 1),
            humidity=humidity,
        )

    @staticmethod
    def _mean_humidity(payload: Any, iso_day: str) -> int:
        hourly = payload.get("hourly") or {}
        times: list[str] = hourly.get("time") or []
        values: list[Any] = hourly.get("relative_humidity_2m") or []
        readings = [
            float(value)
            for stamp, value in zip(times, values, strict=False)
            if stamp.startswith(iso_day) and value is not None
        ]
        if not readings:
            return 0
        return max(0, min(100, round(fmean(readings))))
