"""Weather and currency adapters, plus the Money value object."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from app.core.errors import ProviderUnavailableError
from app.domain.money import Money
from app.providers.currency import ExchangeRateProvider
from app.providers.http_client import ResilientHttpClient
from app.providers.weather import OpenMeteoWeatherProvider


def _provider_client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_money_rejects_bad_currency() -> None:
    with pytest.raises(ValidationError):
        Money(amount_minor=100, currency="US")
    with pytest.raises(ValidationError):
        Money(amount_minor=-1, currency="USD")


def test_money_normalizes_and_formats() -> None:
    money = Money(amount_minor=12345, currency="usd")
    assert money.currency == "USD"
    assert str(money) == "123.45 USD"


async def test_weather_provider_parses_payload() -> None:
    payload = {
        "daily": {
            "temperature_2m_max": [21.4],
            "precipitation_probability_max": [30],
            "wind_speed_10m_max": [12.0],
        },
        "hourly": {
            "time": ["2026-08-10T00:00", "2026-08-10T01:00", "2026-08-11T00:00"],
            "relative_humidity_2m": [50, 60, 90],
        },
    }
    async with _provider_client(lambda _r: httpx.Response(200, json=payload)) as raw:
        client = ResilientHttpClient(raw, provider="open-meteo", backoff_base=0.0)
        provider = OpenMeteoWeatherProvider(client, base_url="http://wx", cache_ttl=0)
        forecast = await provider.forecast(52.0, 13.0, date(2026, 8, 10))

    assert forecast.temperature_c == 21.4
    assert forecast.precipitation_probability == 30
    assert forecast.humidity == 55  # mean of the two 2026-08-10 readings only


async def test_weather_provider_rejects_bad_payload() -> None:
    async with _provider_client(lambda _r: httpx.Response(200, json={"unexpected": 1})) as raw:
        client = ResilientHttpClient(raw, provider="open-meteo", backoff_base=0.0)
        provider = OpenMeteoWeatherProvider(client, base_url="http://wx", cache_ttl=0)
        with pytest.raises(ProviderUnavailableError):
            await provider.forecast(52.0, 13.0, date(2026, 8, 10))


async def test_currency_provider_parses_payload() -> None:
    payload = {"info": {"rate": 1.09}, "result": 109.0, "date": "2026-07-30"}
    async with _provider_client(lambda _r: httpx.Response(200, json=payload)) as raw:
        client = ResilientHttpClient(raw, provider="fx", backoff_base=0.0)
        provider = ExchangeRateProvider(client, base_url="http://fx", cache_ttl=0)
        conversion = await provider.convert("usd", "eur", 100.0)

    assert conversion.base == "USD"
    assert conversion.quote == "EUR"
    assert conversion.rate == 1.09
    assert conversion.converted == 109.0
