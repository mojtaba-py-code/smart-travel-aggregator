"""Auth request/response schemas with strict input validation."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_MIN_PASSWORD_LEN = 10
_MAX_PASSWORD_LEN = 128


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=_MIN_PASSWORD_LEN, max_length=_MAX_PASSWORD_LEN)
    full_name: str | None = Field(default=None, max_length=200)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        # Require some variety without being obnoxious about it.
        if value.isalpha() or value.isdigit():
            raise ValueError("password must mix letters and numbers")
        if value.lower() == value or value.upper() == value:
            raise ValueError("password must contain upper and lower case letters")
        return value

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=_MAX_PASSWORD_LEN)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: str
    is_verified: bool
    created_at: datetime
