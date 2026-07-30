"""Flight search, weather and currency endpoints."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_currency_provider, get_weather_provider
from app.domain.dto import CurrencyConversion, WeatherForecast


async def test_flight_search_returns_ranked_results(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/flights/search",
        params={"origin": "THR", "destination": "IST", "departure_date": "2026-08-10"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"], "expected at least one offer"
    assert body["meta"]["degraded"] is False
    assert body["meta"]["providers_ok"] == 2
    first = body["data"][0]
    assert first["origin"] == "THR"
    assert first["price"]["currency"] == "USD"


async def test_flight_search_sorted_by_price(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/flights/search",
        params={
            "origin": "THR",
            "destination": "IST",
            "departure_date": "2026-08-10",
            "sort": "price",
            "limit": 50,
        },
    )
    prices = [o["price"]["amount_minor"] for o in resp.json()["data"]]
    assert prices == sorted(prices)


async def test_flight_search_same_origin_destination_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/flights/search",
        params={"origin": "THR", "destination": "THR", "departure_date": "2026-08-10"},
    )
    assert resp.status_code == 400


async def test_flight_search_bad_iata_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/flights/search",
        params={"origin": "TEHRAN", "destination": "IST", "departure_date": "2026-08-10"},
    )
    assert resp.status_code == 422


async def test_flight_search_records_history_for_authenticated_user(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get(
        "/api/v1/flights/search",
        params={"origin": "THR", "destination": "DXB", "departure_date": "2026-08-10"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


class FakeWeather:
    name = "fake-weather"

    async def forecast(self, latitude: float, longitude: float, day: date) -> WeatherForecast:
        return WeatherForecast(
            latitude=latitude,
            longitude=longitude,
            date=day.isoformat(),
            temperature_c=25.0,
            precipitation_probability=10,
            wind_kph=8.0,
            humidity=40,
        )


class FakeCurrency:
    name = "fake-fx"

    async def convert(self, base: str, quote: str, amount: float) -> CurrencyConversion:
        return CurrencyConversion(
            base=base.upper(),
            quote=quote.upper(),
            rate=2.0,
            amount=amount,
            converted=amount * 2.0,
            as_of="2026-07-30",
        )


@pytest.fixture
def fake_providers(app: FastAPI) -> None:
    app.dependency_overrides[get_weather_provider] = FakeWeather
    app.dependency_overrides[get_currency_provider] = FakeCurrency


async def test_weather_endpoint(client: httpx.AsyncClient, fake_providers: None) -> None:
    resp = await client.get(
        "/api/v1/weather",
        params={"latitude": 35.7, "longitude": 51.4, "day": "2026-08-10"},
    )
    assert resp.status_code == 200
    assert resp.json()["temperature_c"] == 25.0


async def test_weather_rejects_out_of_range_latitude(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/weather",
        params={"latitude": 999, "longitude": 51.4, "day": "2026-08-10"},
    )
    assert resp.status_code == 422


async def test_currency_endpoint(client: httpx.AsyncClient, fake_providers: None) -> None:
    resp = await client.get(
        "/api/v1/currency/convert",
        params={"base": "USD", "quote": "EUR", "amount": 50},
    )
    assert resp.status_code == 200
    assert resp.json()["converted"] == 100.0
