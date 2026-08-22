"""Authentication endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import (
    AccessPayload,
    CurrentUser,
    SessionDep,
    enforce_rate_limit,
    get_auth_service,
    get_container,
)
from app.db.models import AuditLog
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(enforce_rate_limit)])


def _client_ip(request: Request) -> str | None:
    # Same rules as the rate limiter: the forwarded header counts only when the
    # peer is a proxy we configured, so the audit log records the real caller.
    return get_container(request).proxy_trust.client_ip(request)


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
    session.add(AuditLog(actor_id=user.id, action="user.register", ip_address=_client_ip(request)))
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: SessionDep,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    user = await auth.authenticate(email=payload.email, password=payload.password)
    session.add(AuditLog(actor_id=user.id, action="user.login", ip_address=_client_ip(request)))
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


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    await auth.verify_email(payload.token)
    return MessageResponse(message="email verified")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    payload: ResendVerificationRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    await auth.resend_verification(payload.email)
    # Response is intentionally identical whether or not the address exists.
    return MessageResponse(message="if the account exists, a verification email was sent")


@router.post("/password-reset/request", response_model=MessageResponse)
async def request_password_reset(
    payload: PasswordResetRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    await auth.request_password_reset(payload.email)
    return MessageResponse(message="if the account exists, a reset email was sent")


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    await auth.reset_password(payload.token, payload.new_password)
    return MessageResponse(message="password updated")


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: LogoutRequest,
    access_payload: AccessPayload,
    request: Request,
    session: SessionDep,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    await auth.logout(access_payload, payload.refresh_token)
    session.add(
        AuditLog(
            actor_id=uuid.UUID(access_payload["sub"]),
            action="user.logout",
            ip_address=_client_ip(request),
        )
    )
    return MessageResponse(message="logged out")
