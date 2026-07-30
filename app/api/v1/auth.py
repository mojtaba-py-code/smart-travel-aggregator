"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import CurrentUser, SessionDep, enforce_rate_limit, get_auth_service
from app.db.models import AuditLog
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(enforce_rate_limit)])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: SessionDep,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> UserOut:
    user = await auth.register(
        email=payload.email, password=payload.password, full_name=payload.full_name
    )
    session.add(
        AuditLog(actor_id=user.id, action="user.register", ip_address=_client_ip(request))
    )
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: SessionDep,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    user = await auth.authenticate(email=payload.email, password=payload.password)
    session.add(
        AuditLog(actor_id=user.id, action="user.login", ip_address=_client_ip(request))
    )
    tokens = auth.issue_tokens(user)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    tokens = await auth.refresh(payload.refresh_token)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)
