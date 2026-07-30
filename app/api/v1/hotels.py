"""Hotel search endpoint: validated query -> aggregated, ranked results."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import enforce_rate_limit, get_hotel_service
from app.core.errors import AppError
from app.domain.ports import HotelSearchQuery
from app.schemas.common import MoneyOut, PageInfo
from app.schemas.travel import HotelOfferOut, HotelSearchResponse, SearchMetaOut
from app.services.hotel_aggregation import (
    HotelAggregationService,
    HotelFilters,
    HotelSortKey,
)

router = APIRouter(prefix="/hotels", tags=["hotels"])


@router.get(
    "/search",
    response_model=HotelSearchResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
async def search_hotels(
    service: Annotated[HotelAggregationService, Depends(get_hotel_service)],
    city: Annotated[str, Query(min_length=2, max_length=64, description="Destination city")],
    check_in: Annotated[date, Query(description="Check-in date (YYYY-MM-DD)")],
    check_out: Annotated[date, Query(description="Check-out date (YYYY-MM-DD)")],
    guests: Annotated[int, Query(ge=1, le=8)] = 2,
    sort: HotelSortKey = HotelSortKey.BEST,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
    amenities: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> HotelSearchResponse:
    if check_out <= check_in:
        raise AppError("check-out must be after check-in")

    query = HotelSearchQuery(city=city, check_in=check_in, check_out=check_out, guests=guests)
    filters = HotelFilters(
        max_price_minor=max_price,
        min_rating=min_rating,
        amenities=frozenset(a.lower() for a in amenities) if amenities else frozenset(),
    )
    result = await service.search(query, sort=sort, filters=filters, limit=limit, cursor=cursor)

    return HotelSearchResponse(
        data=[
            HotelOfferOut(
                id=item.hotel.id,
                name=item.hotel.name,
                city=item.hotel.city,
                rating=item.hotel.rating,
                reviews_count=item.hotel.reviews_count,
                price_per_night=MoneyOut(
                    amount_minor=item.hotel.price_per_night.amount_minor,
                    currency=item.hotel.price_per_night.currency,
                ),
                amenities=item.hotel.amenities,
                provider=item.hotel.provider,
                score=item.score,
            )
            for item in result.items
        ],
        page=PageInfo(next_cursor=result.next_cursor, has_more=result.has_more),
        meta=SearchMetaOut(
            degraded=result.meta.degraded,
            providers_ok=result.meta.providers_ok,
            providers_failed=result.meta.providers_failed,
            total=result.meta.total,
        ),
    )
