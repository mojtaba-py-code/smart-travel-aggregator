"""ORM models.

Kept deliberately normalized: a user owns many searches and price alerts; the
audit log is an append-only record of security-relevant events.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(enum.StrEnum):
    USER = "user"
    ADMIN = "admin"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(200), default=None)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=16), default=UserRole.USER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    searches: Mapped[list[SearchHistory]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    price_alerts: Mapped[list[PriceAlert]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SearchHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "search_history"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    origin: Mapped[str] = mapped_column(String(3))
    destination: Mapped[str] = mapped_column(String(3))
    departure_date: Mapped[str] = mapped_column(String(10))
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="searches")

    __table_args__ = (Index("ix_search_route", "origin", "destination"),)


class AlertChannel(enum.StrEnum):
    EMAIL = "email"
    PUSH = "push"


class PriceAlert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "price_alerts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    origin: Mapped[str] = mapped_column(String(3))
    destination: Mapped[str] = mapped_column(String(3))
    departure_date: Mapped[str] = mapped_column(String(10))
    target_amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    channel: Mapped[AlertChannel] = mapped_column(
        Enum(AlertChannel, native_enum=False, length=16), default=AlertChannel.EMAIL
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    user: Mapped[User] = relationship(back_populates="price_alerts")


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_log"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(String(500), default="")
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
