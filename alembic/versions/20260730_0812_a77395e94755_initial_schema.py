"""initial schema

Revision ID: a77395e94755
Revises:
Create Date: 2026-07-30 08:12:24.981303+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a77395e94755"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column(
            "role",
            sa.Enum("USER", "ADMIN", name="userrole", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(length=3), nullable=False),
        sa.Column("destination", sa.String(length=3), nullable=False),
        sa.Column("departure_date", sa.String(length=10), nullable=False),
        sa.Column("target_amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("EMAIL", "PUSH", name="alertchannel", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_price_alerts_user_id"), "price_alerts", ["user_id"], unique=False)
    op.create_table(
        "search_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(length=3), nullable=False),
        sa.Column("destination", sa.String(length=3), nullable=False),
        sa.Column("departure_date", sa.String(length=10), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_search_history_user_id"), "search_history", ["user_id"], unique=False)
    op.create_index("ix_search_route", "search_history", ["origin", "destination"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_search_route", table_name="search_history")
    op.drop_index(op.f("ix_search_history_user_id"), table_name="search_history")
    op.drop_table("search_history")
    op.drop_index(op.f("ix_price_alerts_user_id"), table_name="price_alerts")
    op.drop_table("price_alerts")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_audit_log_actor_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_table("audit_log")
