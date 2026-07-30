"""Flight search endpoint: validated query -> aggregated, ranked results."""

from __future__ import annotations

import time
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    OptionalUser,
    SessionDep,
    enforce_rate_limit,
    get_flight_service,
)
from app.core.errors import AppError
from app.db.models import SearchHistory
from app.domain.ports import FlightSearchQuery
from app.schemas.common import MoneyOut, PageInfo
from app.schemas.travel import (
    FlightOfferOut,
    FlightSearchResponse,
    SearchMetaOut,
)
from app.services.aggregation import (
    FlightAggregationService,
    FlightFilters,
    SortKey,
)

router = APIRouter(prefix="/flights", tags=["flights"])

_IATA = r"^[A-Za-z]{3}$"


@router.get(
    "/search",
    response_model=FlightSearchResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
async def search_flights(
    session: SessionDep,
    current_user: OptionalUser,
    service: Annotated[FlightAggregationService, Depends(get_flight_service)],
    origin: Annotated[str, Query(pattern=_IATA, description="Origin IATA code")],
    destination: Annotated[str, Query(pattern=_IATA, description="Destination IATA code")],
    departure_date: Annotated[date, Query(description="Departure date (YYYY-MM-DD)")],
    adults: Annotated[int, Query(ge=1, le=9)] = 1,
    cabin: Annotated[str, Query(pattern=r"^(economy|premium|business|first)$")] = "economy",
    sort: SortKey = SortKey.BEST,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    max_stops: Annotated[int | None, Query(ge=0, le=3)] = None,
    airlines: Annotated[list[str] | None, Query()] = None,
    direct_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> FlightSearchResponse:
    if origin.upper() == destination.upper():
        raise AppError("origin and destination must differ")

    query = FlightSearchQuery(
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=departure_date,
        adults=adults,
        cabin_class=cabin,
    )
    filters = FlightFilters(
        max_price_minor=max_price,
        max_stops=max_stops,
        airlines=frozenset(a.lower() for a in airlines) if airlines else frozenset(),
        direct_only=direct_only,
    )

    started = time.perf_counter()
    result = await service.search(query, sort=sort, filters=filters, limit=limit, cursor=cursor)
    latency_ms = int((time.perf_counter() - started) * 1000)

    if current_user is not None:
        session.add(
            SearchHistory(
                user_id=current_user.id,
                origin=query.origin,
                destination=query.destination,
                departure_date=departure_date.isoformat(),
                result_count=result.meta.total,
                latency_ms=latency_ms,
            )
        )

    return FlightSearchResponse(
        data=[
            FlightOfferOut(
                id=item.flight.id,
                airline=item.flight.airline,
                origin=item.flight.origin,
                destination=item.flight.destination,
                departure_time=item.flight.departure_time,
                arrival_time=item.flight.arrival_time,
                duration_minutes=item.flight.duration_minutes,
                stops=item.flight.stops,
                cabin_class=item.flight.cabin_class,
                price=MoneyOut(
                    amount_minor=item.flight.price.amount_minor,
                    currency=item.flight.price.currency,
                ),
                provider=item.flight.provider,
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
