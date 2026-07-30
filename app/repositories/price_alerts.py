"""Price-alert persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertChannel, PriceAlert


class PriceAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        origin: str,
        destination: str,
        departure_date: str,
        target_amount_minor: int,
        currency: str,
        channel: AlertChannel,
    ) -> PriceAlert:
        alert = PriceAlert(
            user_id=user_id,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            target_amount_minor=target_amount_minor,
            currency=currency,
            channel=channel,
        )
        self._session.add(alert)
        await self._session.flush()
        return alert

    async def list_for_user(self, user_id: uuid.UUID) -> list[PriceAlert]:
        result = await self._session.execute(
            select(PriceAlert)
            .where(PriceAlert.user_id == user_id)
            .order_by(PriceAlert.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_owned(self, alert_id: uuid.UUID, user_id: uuid.UUID) -> PriceAlert | None:
        result = await self._session.execute(
            select(PriceAlert).where(PriceAlert.id == alert_id, PriceAlert.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, alert: PriceAlert) -> None:
        await self._session.delete(alert)
        await self._session.flush()

    async def list_active(self) -> list[PriceAlert]:
        result = await self._session.execute(
            select(PriceAlert).where(PriceAlert.is_active.is_(True))
        )
        return list(result.scalars().all())
