"""Uniform error handling using RFC 7807 "Problem Details".

Every error the API emits — whether a raised ``AppError``, a validation
failure, or an unexpected exception — is rendered as
``application/problem+json`` with a stable machine-readable ``code`` and the
request's ``trace_id``. Internal errors never leak stack traces to clients.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_ctx

logger = get_logger("errors")

PROBLEM_CONTENT_TYPE = "application/problem+json"


class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    title: str = "Bad Request"

    def __init__(self, detail: str, *, extra: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra or {}


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    title = "Resource Not Found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    title = "Conflict"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    title = "Authentication Failed"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    title = "Permission Denied"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    title = "Too Many Requests"


class ProviderUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "provider_unavailable"
    title = "Upstream Provider Unavailable"


def _problem(
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://smarttravel.dev/errors/{code}",
        "title": title,
        "status": status_code,
        "code": code,
        "detail": detail,
        "trace_id": request_id_ctx.get(),
    }
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content=body, media_type=PROBLEM_CONTENT_TYPE)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _problem(
            status_code=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            extra=exc.extra,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            title="Request Validation Failed",
            detail="One or more fields are invalid.",
            extra={"errors": _clean_validation_errors(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(
            status_code=exc.status_code,
            code="http_error",
            title="HTTP Error",
            detail=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Log the real error server-side; return a generic message to the client.
        logger.error("unhandled_exception", error=str(exc), error_type=type(exc).__name__)
        return _problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            title="Internal Server Error",
            detail="An unexpected error occurred. The incident has been logged.",
        )


def _clean_validation_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for err in errors:
        loc = [str(part) for part in err.get("loc", []) if part != "body"]
        cleaned.append(
            {"field": ".".join(loc) or "body", "message": err.get("msg", "invalid value")}
        )
    return cleaned
