"""Flight aggregation: fan-out, de-duplication, ranking and pagination.

The service queries every configured provider concurrently. A provider that
fails or times out is dropped from the merge (its offers are simply absent) and
the response is flagged ``degraded`` rather than failing the whole request.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from enum import StrEnum

from app.core.logging import get_logger
from app.domain.dto import NormalizedFlight
from app.domain.ports import FlightProvider, FlightSearchQuery

logger = get_logger("aggregation")


class SortKey(StrEnum):
    BEST = "best"
    PRICE = "price"
    DURATION = "duration"
    DEPARTURE = "departure"
    STOPS = "stops"


@dataclass(frozen=True, slots=True)
class FlightFilters:
    max_price_minor: int | None = None
    max_stops: int | None = None
    airlines: frozenset[str] = field(default_factory=frozenset)
    direct_only: bool = False

    def matches(self, flight: NormalizedFlight) -> bool:
        if self.direct_only and not flight.is_direct:
            return False
        if self.max_stops is not None and flight.stops > self.max_stops:
            return False
        if self.max_price_minor is not None and flight.price.amount_minor > self.max_price_minor:
            return False
        return not (self.airlines and flight.airline.lower() not in self.airlines)


@dataclass(frozen=True, slots=True)
class RankedFlight:
    flight: NormalizedFlight
    score: float


@dataclass(frozen=True, slots=True)
class SearchMeta:
    degraded: bool
    providers_ok: int
    providers_failed: int
    total: int


@dataclass(frozen=True, slots=True)
class AggregationResult:
    items: list[RankedFlight]
    meta: SearchMeta
    next_cursor: str | None
    has_more: bool


class FlightAggregationService:
    def __init__(self, providers: list[FlightProvider]) -> None:
        if not providers:
            raise ValueError("at least one flight provider is required")
        self._providers = providers

    async def search(
        self,
        query: FlightSearchQuery,
        *,
        sort: SortKey = SortKey.BEST,
        filters: FlightFilters | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> AggregationResult:
        filters = filters or FlightFilters()
        flights, ok, failed = await self._fan_out(query)

        deduped = self._dedupe(flights)
        filtered = [f for f in deduped if filters.matches(f)]
        ranked = self._rank(filtered)
        ordered = self._sort(ranked, sort)

        offset = _decode_cursor(cursor)
        page = ordered[offset : offset + limit]
        has_more = offset + limit < len(ordered)
        next_cursor = _encode_cursor(offset + limit) if has_more else None

        return AggregationResult(
            items=page,
            meta=SearchMeta(
                degraded=failed > 0,
                providers_ok=ok,
                providers_failed=failed,
                total=len(ordered),
            ),
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def _fan_out(self, query: FlightSearchQuery) -> tuple[list[NormalizedFlight], int, int]:
        results = await asyncio.gather(
            *(provider.search(query) for provider in self._providers),
            return_exceptions=True,
        )
        flights: list[NormalizedFlight] = []
        ok = failed = 0
        for provider, result in zip(self._providers, results, strict=True):
            if isinstance(result, BaseException):
                failed += 1
                logger.warning("provider_failed", provider=provider.name, error=str(result))
                continue
            ok += 1
            flights.extend(result)
        return flights, ok, failed

    @staticmethod
    def _dedupe(flights: list[NormalizedFlight]) -> list[NormalizedFlight]:
        # Same physical flight offered by several providers -> keep the cheapest.
        best: dict[tuple[str, str, str, str], NormalizedFlight] = {}
        for flight in flights:
            key = (
                flight.airline.lower(),
                flight.origin,
                flight.destination,
                flight.departure_time.isoformat(),
            )
            existing = best.get(key)
            if existing is None or flight.price.amount_minor < existing.price.amount_minor:
                best[key] = flight
        return list(best.values())

    @staticmethod
    def _rank(flights: list[NormalizedFlight]) -> list[RankedFlight]:
        if not flights:
            return []
        prices = [f.price.amount_minor for f in flights]
        durations = [f.duration_minutes for f in flights]
        min_price, min_duration = min(prices), min(durations)
        max_stops = max((f.stops for f in flights), default=0)
        price_span = max(prices) - min_price
        duration_span = max(durations) - min_duration

        ranked: list[RankedFlight] = []
        for flight in flights:
            price_norm = (flight.price.amount_minor - min_price) / price_span if price_span else 0.0
            duration_norm = (
                (flight.duration_minutes - min_duration) / duration_span if duration_span else 0.0
            )
            stops_norm = flight.stops / max_stops if max_stops else 0.0
            penalty = 0.5 * price_norm + 0.3 * duration_norm + 0.2 * stops_norm
            ranked.append(RankedFlight(flight=flight, score=round(1 - penalty, 3)))
        return ranked

    @staticmethod
    def _sort(ranked: list[RankedFlight], sort: SortKey) -> list[RankedFlight]:
        keys = {
            SortKey.BEST: lambda r: -r.score,
            SortKey.PRICE: lambda r: r.flight.price.amount_minor,
            SortKey.DURATION: lambda r: r.flight.duration_minutes,
            SortKey.DEPARTURE: lambda r: r.flight.departure_time,
            SortKey.STOPS: lambda r: r.flight.stops,
        }
        return sorted(ranked, key=keys[sort])


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, TypeError):
        return 0
    return max(0, offset)
