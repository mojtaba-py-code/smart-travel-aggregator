"""Hotel aggregation service and the /hotels/search endpoint."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.domain.dto import NormalizedHotel
from app.domain.money import Money
from app.domain.ports import HotelSearchQuery
from app.services.hotel_aggregation import (
    HotelAggregationService,
    HotelFilters,
    HotelSortKey,
)

QUERY = HotelSearchQuery(
    city="Istanbul", check_in=date(2026, 8, 10), check_out=date(2026, 8, 13), guests=2
)


def _hotel(*, name: str, city: str, price: int, rating: float, reviews: int, amenities: list[str]):
    return NormalizedHotel(
        id=f"{name}-{price}",
        provider="p",
        name=name,
        city=city,
        rating=rating,
        reviews_count=reviews,
        price_per_night=Money(amount_minor=price, currency="USD"),
        amenities=amenities,
    )


class StaticHotels:
    def __init__(self, name: str, hotels: list[NormalizedHotel]) -> None:
        self.name = name
        self._hotels = hotels

    async def search(self, _query: HotelSearchQuery) -> list[NormalizedHotel]:
        return self._hotels


class BrokenHotels:
    name = "broken"

    async def search(self, _query: HotelSearchQuery) -> list[NormalizedHotel]:
        raise RuntimeError("down")


def test_query_nights() -> None:
    assert QUERY.nights == 3


def test_requires_provider() -> None:
    with pytest.raises(ValueError, match="at least one"):
        HotelAggregationService([])


async def test_degraded_when_provider_fails() -> None:
    good = StaticHotels(
        "a",
        [
            _hotel(
                name="Central Inn",
                city="Istanbul",
                price=9000,
                rating=4.5,
                reviews=200,
                amenities=["wifi"],
            )
        ],
    )
    service = HotelAggregationService([good, BrokenHotels()])
    result = await service.search(QUERY)
    assert result.meta.degraded is True
    assert result.meta.providers_failed == 1
    assert len(result.items) == 1


async def test_dedupe_keeps_cheapest() -> None:
    a = _hotel(
        name="Park Hotel", city="Istanbul", price=15000, rating=4.0, reviews=100, amenities=[]
    )
    b = _hotel(
        name="park hotel", city="istanbul", price=11000, rating=4.0, reviews=100, amenities=[]
    )
    service = HotelAggregationService([StaticHotels("a", [a]), StaticHotels("b", [b])])
    result = await service.search(QUERY)
    assert len(result.items) == 1
    assert result.items[0].hotel.price_per_night.amount_minor == 11000


async def test_filters_rating_and_amenities() -> None:
    hotels = [
        _hotel(
            name="A",
            city="Istanbul",
            price=9000,
            rating=4.8,
            reviews=500,
            amenities=["wifi", "pool"],
        ),
        _hotel(name="B", city="Istanbul", price=8000, rating=3.2, reviews=50, amenities=["wifi"]),
        _hotel(name="C", city="Istanbul", price=9500, rating=4.6, reviews=300, amenities=["wifi"]),
    ]
    service = HotelAggregationService([StaticHotels("a", hotels)])
    result = await service.search(
        QUERY, filters=HotelFilters(min_rating=4.5, amenities=frozenset({"pool"}))
    )
    assert {i.hotel.name for i in result.items} == {"A"}


async def test_sort_by_price() -> None:
    hotels = [
        _hotel(name="A", city="Istanbul", price=20000, rating=4.0, reviews=1, amenities=[]),
        _hotel(name="B", city="Istanbul", price=8000, rating=4.0, reviews=1, amenities=[]),
        _hotel(name="C", city="Istanbul", price=12000, rating=4.0, reviews=1, amenities=[]),
    ]
    service = HotelAggregationService([StaticHotels("a", hotels)])
    result = await service.search(QUERY, sort=HotelSortKey.PRICE)
    prices = [i.hotel.price_per_night.amount_minor for i in result.items]
    assert prices == sorted(prices)


# --- API ---------------------------------------------------------------------


async def test_hotel_search_endpoint(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/hotels/search",
        params={"city": "Istanbul", "check_in": "2026-08-10", "check_out": "2026-08-13"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]
    assert body["meta"]["providers_ok"] == 2
    first = body["data"][0]
    assert first["city"] == "Istanbul"
    assert first["price_per_night"]["currency"] == "USD"


async def test_hotel_search_checkout_before_checkin_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/hotels/search",
        params={"city": "Istanbul", "check_in": "2026-08-13", "check_out": "2026-08-10"},
    )
    assert resp.status_code == 400


async def test_hotel_search_validates_city(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/hotels/search",
        params={"city": "X", "check_in": "2026-08-10", "check_out": "2026-08-13"},
    )
    assert resp.status_code == 422
