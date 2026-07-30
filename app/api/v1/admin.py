"""Admin dashboard metrics (admin role required)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import AdminUser, SessionDep
from app.db.models import PriceAlert, SearchHistory, User

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminMetrics(BaseModel):
    total_users: int
    total_searches: int
    active_alerts: int
    popular_routes: list[dict[str, object]]


@router.get("/metrics", response_model=AdminMetrics)
async def metrics(_: AdminUser, session: SessionDep) -> AdminMetrics:
    total_users = await session.scalar(select(func.count()).select_from(User)) or 0
    total_searches = await session.scalar(select(func.count()).select_from(SearchHistory)) or 0
    active_alerts = (
        await session.scalar(
            select(func.count()).select_from(PriceAlert).where(PriceAlert.is_active.is_(True))
        )
        or 0
    )

    route_rows = await session.execute(
        select(
            SearchHistory.origin,
            SearchHistory.destination,
            func.count().label("searches"),
        )
        .group_by(SearchHistory.origin, SearchHistory.destination)
        .order_by(func.count().desc())
        .limit(10)
    )
    popular = [
        {"route": f"{origin}-{destination}", "searches": searches}
        for origin, destination, searches in route_rows.all()
    ]

    return AdminMetrics(
        total_users=total_users,
        total_searches=total_searches,
        active_alerts=active_alerts,
        popular_routes=popular,
    )
