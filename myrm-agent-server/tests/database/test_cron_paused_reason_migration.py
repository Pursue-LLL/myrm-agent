"""Existing databases must gain ``cron_jobs.paused_reason`` through the append-only migration list."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base


async def _cron_job_columns(engine: AsyncEngine) -> dict[str, tuple[str, int]]:
    """Column name to its declared type and its NOT NULL flag."""
    async with engine.connect() as conn:
        rows = await conn.execute(text("PRAGMA table_info(cron_jobs)"))
        return {row[1]: (row[2], row[3]) for row in rows}


@pytest.mark.asyncio
async def test_run_migrations_adds_a_nullable_paused_reason_to_existing_cron_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # An upgrading database still carries the message_filter_config table that a later migration alters.
            await conn.execute(text("CREATE TABLE message_filter_config (id INTEGER PRIMARY KEY, pii_mode VARCHAR(50))"))
            await conn.execute(text("ALTER TABLE cron_jobs DROP COLUMN paused_reason"))
        assert "paused_reason" not in await _cron_job_columns(engine)

        full_list = list(migrations.MIGRATION_STATEMENTS)
        added_at = next(i for i, stmt in enumerate(full_list) if "cron_jobs ADD COLUMN paused_reason" in stmt)
        # An upgrading user already recorded every migration that preceded the paused_reason statement.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[:added_at])
        await migrations.run_migrations(engine)
        assert "paused_reason" not in await _cron_job_columns(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        # Jobs that were paused before the column existed need no backfill: no reason is what they have.
        assert (await _cron_job_columns(engine))["paused_reason"] == ("VARCHAR(20)", 0)
    finally:
        await engine.dispose()
