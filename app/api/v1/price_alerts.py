"""Price-alert CRUD for authenticated users."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, SessionDep, enforce_rate_limit
from app.core.errors import AppError, NotFoundError
from app.db.models import AlertChannel
from app.repositories.price_alerts import PriceAlertRepository
from app.schemas.travel import PriceAlertCreate, PriceAlertOut

router = APIRouter(
    prefix="/price-alerts",
    tags=["price-alerts"],
    dependencies=[Depends(enforce_rate_limit)],
)


@router.post("", response_model=PriceAlertOut, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: PriceAlertCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> PriceAlertOut:
    if payload.origin.upper() == payload.destination.upper():
        raise AppError("origin and destination must differ")

    alert = await PriceAlertRepository(session).create(
        user_id=current_user.id,
        origin=payload.origin.upper(),
        destination=payload.destination.upper(),
        departure_date=payload.departure_date,
        target_amount_minor=payload.target_amount_minor,
        currency=payload.currency.upper(),
        channel=AlertChannel(payload.channel),
    )
    return PriceAlertOut.model_validate(alert, from_attributes=True)


@router.get("", response_model=list[PriceAlertOut])
async def list_alerts(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[PriceAlertOut]:
    alerts = await PriceAlertRepository(session).list_for_user(current_user.id)
    return [PriceAlertOut.model_validate(a, from_attributes=True) for a in alerts]


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: str,
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    try:
        parsed = uuid.UUID(alert_id)
    except ValueError as exc:
        raise NotFoundError("alert not found") from exc

    repo = PriceAlertRepository(session)
    alert = await repo.get_owned(parsed, current_user.id)
    if alert is None:
        raise NotFoundError("alert not found")
    await repo.delete(alert)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
