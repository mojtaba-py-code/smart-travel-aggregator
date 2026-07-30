"""Currency conversion endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import enforce_rate_limit, get_currency_provider
from app.domain.ports import CurrencyProvider
from app.schemas.travel import CurrencyOut

router = APIRouter(prefix="/currency", tags=["currency"])


@router.get("/convert", response_model=CurrencyOut, dependencies=[Depends(enforce_rate_limit)])
async def convert_currency(
    provider: Annotated[CurrencyProvider, Depends(get_currency_provider)],
    base: Annotated[str, Query(pattern=r"^[A-Za-z]{3}$", description="Source currency")],
    quote: Annotated[str, Query(pattern=r"^[A-Za-z]{3}$", description="Target currency")],
    amount: Annotated[float, Query(gt=0)] = 1.0,
) -> CurrencyOut:
    conversion = await provider.convert(base, quote, amount)
    return CurrencyOut(**conversion.model_dump())
