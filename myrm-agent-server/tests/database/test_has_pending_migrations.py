"""has_pending_migrations separates an upgrade from a start that has nothing left to migrate."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def _has_state_table(engine: AsyncEngine) -> bool:
    async with engine.connect() as conn:
        row = await conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_schema_migrations'"))
        return row.scalar() is not None


async def test_a_database_that_never_ran_the_engine_is_pending_and_stays_untouched(engine: AsyncEngine) -> None:
    assert await migrations.has_pending_migrations(engine) is True

    assert not await _has_state_table(engine)


async def test_nothing_is_pending_once_every_statement_is_recorded(engine: AsyncEngine) -> None:
    await migrations.run_migrations(engine)

    assert await migrations.has_pending_migrations(engine) is False


async def test_a_statement_shipped_after_the_last_run_is_pending(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    await migrations.run_migrations(engine)
    shipped_later = [*migrations.MIGRATION_STATEMENTS, "CREATE TABLE shipped_later (id INTEGER PRIMARY KEY)"]
    monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", shipped_later)

    assert await migrations.has_pending_migrations(engine) is True

    await migrations.run_migrations(engine)
    assert await migrations.has_pending_migrations(engine) is False
