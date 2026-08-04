"""One-shot startup task: make sure the database schema exists.

The hosted demo runs on SQLite with an ephemeral disk, so replaying the full
Alembic migration history on every boot adds nothing — the ORM models are the
single source of truth. This creates any missing tables and exits.

Real (Postgres) deployments run ``alembic upgrade head`` instead; this module
is only wired into the demo start command.
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.db import models  # noqa: F401 - imported so every table registers on Base
from app.db.base import Base
from app.db.session import create_engine


async def _create_schema() -> None:
    engine = create_engine(get_settings())
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_create_schema())


if __name__ == "__main__":
    main()
