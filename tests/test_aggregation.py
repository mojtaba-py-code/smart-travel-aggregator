"""Flight aggregation: fan-out, dedupe, ranking, sorting, filtering, paging."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.dto import NormalizedFlight
from app.domain.money import Money
from app.domain.ports import FlightSearchQuery
from app.services.aggregation import (
    FlightAggregationService,
    FlightFilters,
    SortKey,
)

QUERY = FlightSearchQuery(
    origin="THR", destination="IST", departure_date=datetime(2026, 8, 10).date()
)


def _flight(
    *, provider: str, airline: str, price: int, stops: int, duration: int, hour: int, offer: str
) -> NormalizedFlight:
    departure = datetime(2026, 8, 10, hour, 0, tzinfo=UTC)
    return NormalizedFlight(
        id=offer,
        provider=provider,
        airline=airline,
        origin="THR",
        destination="IST",
        departure_time=departure,
        arrival_time=departure,
        duration_minutes=duration,
        stops=stops,
        cabin_class="economy",
        price=Money(amount_minor=price, currency="USD"),
    )


class StaticProvider:
    def __init__(self, name: str, flights: list[NormalizedFlight]) -> None:
        self.name = name
        self._flights = flights

    async def search(self, _query: FlightSearchQuery) -> list[NormalizedFlight]:
        return self._flights


class BrokenProvider:
    name = "broken"

    async def search(self, _query: FlightSearchQuery) -> list[NormalizedFlight]:
        raise RuntimeError("provider exploded")


def test_service_requires_a_provider() -> None:
    with pytest.raises(ValueError, match="at least one"):
        FlightAggregationService([])


async def test_fan_out_merges_and_marks_degraded() -> None:
    offer = _flight(
        provider="a", airline="KLM", price=15000, stops=0, duration=120, hour=8, offer="a1"
    )
    service = FlightAggregationService([StaticProvider("a", [offer]), BrokenProvider()])
    result = await service.search(QUERY)

    assert result.meta.providers_ok == 1
    assert result.meta.providers_failed == 1
    assert result.meta.degraded is True
    assert len(result.items) == 1


async def test_dedupe_keeps_cheapest_of_identical_flight() -> None:
    expensive = _flight(
        provider="a", airline="KLM", price=20000, stops=0, duration=120, hour=8, offer="a1"
    )
    cheap = _flight(
        provider="b", airline="klm", price=14000, stops=0, duration=120, hour=8, offer="b1"
    )
    service = FlightAggregationService(
        [StaticProvider("a", [expensive]), StaticProvider("b", [cheap])]
    )
    result = await service.search(QUERY)

    assert len(result.items) == 1
    assert result.items[0].flight.price.amount_minor == 14000


async def test_sorting_by_price() -> None:
    flights = [
        _flight(provider="a", airline="A", price=30000, stops=0, duration=100, hour=9, offer="1"),
        _flight(provider="a", airline="B", price=10000, stops=1, duration=200, hour=10, offer="2"),
        _flight(provider="a", airline="C", price=20000, stops=0, duration=150, hour=11, offer="3"),
    ]
    service = FlightAggregationService([StaticProvider("a", flights)])
    result = await service.search(QUERY, sort=SortKey.PRICE)
    prices = [i.flight.price.amount_minor for i in result.items]
    assert prices == sorted(prices)


async def test_best_sort_prefers_cheaper_faster_direct() -> None:
    good = _flight(provider="a", airline="A", price=10000, stops=0, duration=100, hour=9, offer="1")
    bad = _flight(provider="a", airline="B", price=30000, stops=2, duration=300, hour=10, offer="2")
    service = FlightAggregationService([StaticProvider("a", [bad, good])])
    result = await service.search(QUERY, sort=SortKey.BEST)
    assert result.items[0].flight.id == "1"
    assert result.items[0].score > result.items[1].score


async def test_filters_direct_and_max_price() -> None:
    flights = [
        _flight(provider="a", airline="A", price=10000, stops=0, duration=100, hour=9, offer="1"),
        _flight(provider="a", airline="B", price=90000, stops=0, duration=120, hour=10, offer="2"),
        _flight(provider="a", airline="C", price=12000, stops=2, duration=200, hour=11, offer="3"),
    ]
    service = FlightAggregationService([StaticProvider("a", flights)])
    result = await service.search(
        QUERY, filters=FlightFilters(direct_only=True, max_price_minor=50000)
    )
    ids = {i.flight.id for i in result.items}
    assert ids == {"1"}


async def test_pagination_cursor() -> None:
    flights = [
        _flight(
            provider="a",
            airline=f"A{i}",
            price=10000 + i,
            stops=0,
            duration=100,
            hour=6,
            offer=str(i),
        )
        for i in range(5)
    ]
    service = FlightAggregationService([StaticProvider("a", flights)])
    page1 = await service.search(QUERY, sort=SortKey.PRICE, limit=2)
    assert len(page1.items) == 2
    assert page1.has_more is True

    page2 = await service.search(QUERY, sort=SortKey.PRICE, limit=2, cursor=page1.next_cursor)
    assert len(page2.items) == 2
    assert {i.flight.id for i in page1.items}.isdisjoint({i.flight.id for i in page2.items})
