"""Shared response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class MoneyOut(BaseModel):
    amount_minor: int
    currency: str


class PageInfo(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class HealthOut(BaseModel):
    status: str
    version: str
