"""FastAPI dependencies: settings, DB session, current user, rate limiting.

Everything is resolved from the :class:`Container` on ``app.state`` so tests
can swap collaborators with ``app.dependency_overrides``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.core.config import Settings
from app.core.errors import AuthenticationError, PermissionDeniedError, RateLimitedError
from app.core.security import TokenError, decode_token
from app.db.models import User, UserRole
from app.domain.ports import CurrencyProvider, WeatherProvider
from app.repositories.users import UserRepository
from app.services.aggregation import FlightAggregationService
from app.services.auth_service import AuthService
from app.services.hotel_aggregation import HotelAggregationService

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_settings_dep(container: Annotated[Container, Depends(get_container)]) -> Settings:
    return container.settings


async def get_session(
    container: Annotated[Container, Depends(get_container)],
) -> AsyncIterator[AsyncSession]:
    async with container.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_user_repository(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def get_auth_service(
    session: SessionDep,
    settings: SettingsDep,
    container: Annotated[Container, Depends(get_container)],
) -> AuthService:
    return AuthService(
        UserRepository(session),
        settings,
        notifier=container.notifier,
        blocklist=container.token_blocklist,
    )


def get_flight_service(
    container: Annotated[Container, Depends(get_container)],
) -> FlightAggregationService:
    return container.flight_service


def get_hotel_service(
    container: Annotated[Container, Depends(get_container)],
) -> HotelAggregationService:
    return container.hotel_service


def get_weather_provider(
    container: Annotated[Container, Depends(get_container)],
) -> WeatherProvider:
    return container.weather_provider


def get_currency_provider(
    container: Annotated[Container, Depends(get_container)],
) -> CurrencyProvider:
    return container.currency_provider


async def enforce_rate_limit(
    request: Request, container: Annotated[Container, Depends(get_container)]
) -> None:
    identity = container.proxy_trust.client_ip(request) or "anonymous"
    allowed, remaining = await container.rate_limiter.check(identity)
    request.state.rate_limit_remaining = remaining
    if not allowed:
        raise RateLimitedError(
            "rate limit exceeded, slow down",
            extra={"limit_per_minute": container.rate_limiter.limit},
        )


async def get_access_payload(
    settings: SettingsDep,
    container: Annotated[Container, Depends(get_container)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any]:
    if credentials is None:
        raise AuthenticationError("missing bearer token")
    try:
        payload = decode_token(credentials.credentials, expected_type="access", settings=settings)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc
    if await container.token_blocklist.is_revoked(payload):
        raise AuthenticationError("this session has been revoked")
    return payload


AccessPayload = Annotated[dict[str, Any], Depends(get_access_payload)]


async def get_current_user(session: SessionDep, payload: AccessPayload) -> User:
    user = await UserRepository(session).get_by_id(uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("user no longer exists or is disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials, expected_type="access", settings=settings)
    except TokenError:
        return None
    return await UserRepository(session).get_by_id(uuid.UUID(payload["sub"]))


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise PermissionDeniedError("admin privileges required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
