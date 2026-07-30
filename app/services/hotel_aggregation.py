"""Hotel aggregation: fan-out, de-duplication, ranking and pagination.

Mirrors the flight aggregation contract. Providers are queried concurrently; a
failing provider is dropped and the response is flagged ``degraded`` rather than
failing the whole request.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum

from app.core.logging import get_logger
from app.domain.dto import NormalizedHotel
from app.domain.ports import HotelProvider, HotelSearchQuery
from app.services.aggregation import SearchMeta
from app.services.pagination import decode_cursor, encode_cursor

logger = get_logger("hotel_aggregation")


class HotelSortKey(StrEnum):
    BEST = "best"
    PRICE = "price"
    RATING = "rating"
    REVIEWS = "reviews"


@dataclass(frozen=True, slots=True)
class HotelFilters:
    max_price_minor: int | None = None
    min_rating: float | None = None
    amenities: frozenset[str] = field(default_factory=frozenset)

    def matches(self, hotel: NormalizedHotel) -> bool:
        if self.min_rating is not None and hotel.rating < self.min_rating:
            return False
        if (
            self.max_price_minor is not None
            and hotel.price_per_night.amount_minor > self.max_price_minor
        ):
            return False
        return self.amenities.issubset(hotel.amenities)


@dataclass(frozen=True, slots=True)
class RankedHotel:
    hotel: NormalizedHotel
    score: float


@dataclass(frozen=True, slots=True)
class HotelResult:
    items: list[RankedHotel]
    meta: SearchMeta
    next_cursor: str | None
    has_more: bool


class HotelAggregationService:
    def __init__(self, providers: list[HotelProvider]) -> None:
        if not providers:
            raise ValueError("at least one hotel provider is required")
        self._providers = providers

    async def search(
        self,
        query: HotelSearchQuery,
        *,
        sort: HotelSortKey = HotelSortKey.BEST,
        filters: HotelFilters | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> HotelResult:
        filters = filters or HotelFilters()
        hotels, ok, failed = await self._fan_out(query)

        deduped = self._dedupe(hotels)
        filtered = [h for h in deduped if filters.matches(h)]
        ranked = self._rank(filtered)
        ordered = self._sort(ranked, sort)

        offset = decode_cursor(cursor)
        page = ordered[offset : offset + limit]
        has_more = offset + limit < len(ordered)
        next_cursor = encode_cursor(offset + limit) if has_more else None

        return HotelResult(
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

    async def _fan_out(self, query: HotelSearchQuery) -> tuple[list[NormalizedHotel], int, int]:
        results = await asyncio.gather(
            *(provider.search(query) for provider in self._providers),
            return_exceptions=True,
        )
        hotels: list[NormalizedHotel] = []
        ok = failed = 0
        for provider, result in zip(self._providers, results, strict=True):
            if isinstance(result, BaseException):
                failed += 1
                logger.warning("provider_failed", provider=provider.name, error=str(result))
                continue
            ok += 1
            hotels.extend(result)
        return hotels, ok, failed

    @staticmethod
    def _dedupe(hotels: list[NormalizedHotel]) -> list[NormalizedHotel]:
        # Same hotel offered by several providers -> keep the cheapest.
        best: dict[tuple[str, str], NormalizedHotel] = {}
        for hotel in hotels:
            key = (hotel.name.lower(), hotel.city.lower())
            existing = best.get(key)
            current = hotel.price_per_night.amount_minor
            if existing is None or current < existing.price_per_night.amount_minor:
                best[key] = hotel
        return list(best.values())

    @staticmethod
    def _rank(hotels: list[NormalizedHotel]) -> list[RankedHotel]:
        if not hotels:
            return []
        prices = [h.price_per_night.amount_minor for h in hotels]
        min_price = min(prices)
        price_span = max(prices) - min_price

        ranked: list[RankedHotel] = []
        for hotel in hotels:
            price_norm = (
                (hotel.price_per_night.amount_minor - min_price) / price_span if price_span else 0.0
            )
            rating_norm = hotel.rating / 5.0
            # Reward rating, penalise price.
            score = round(0.6 * rating_norm + 0.4 * (1 - price_norm), 3)
            ranked.append(RankedHotel(hotel=hotel, score=score))
        return ranked

    @staticmethod
    def _sort(ranked: list[RankedHotel], sort: HotelSortKey) -> list[RankedHotel]:
        keys = {
            HotelSortKey.BEST: lambda r: -r.score,
            HotelSortKey.PRICE: lambda r: float(r.hotel.price_per_night.amount_minor),
            HotelSortKey.RATING: lambda r: -r.hotel.rating,
            HotelSortKey.REVIEWS: lambda r: float(-r.hotel.reviews_count),
        }
        return sorted(ranked, key=keys[sort])
