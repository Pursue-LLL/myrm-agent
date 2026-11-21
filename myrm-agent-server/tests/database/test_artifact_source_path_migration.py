"""Existing databases must gain ``artifacts.source_path`` through the append-only migration list."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base


async def _artifact_columns(engine: AsyncEngine) -> dict[str, tuple[str, int]]:
    """Column name to its declared type and its NOT NULL flag."""
    async with engine.connect() as conn:
        rows = await conn.execute(text("PRAGMA table_info(artifacts)"))
        return {row[1]: (row[2], row[3]) for row in rows}


@pytest.mark.asyncio
async def test_run_migrations_adds_a_nullable_source_path_to_existing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # An upgrading database still carries the message_filter_config table that a later migration alters.
            await conn.execute(text("CREATE TABLE message_filter_config (id INTEGER PRIMARY KEY, pii_mode VARCHAR(50))"))
            await conn.execute(text("ALTER TABLE artifacts DROP COLUMN source_path"))
            await conn.execute(
                text(
                    "INSERT INTO artifacts (id, name, is_deleted, created_at, updated_at) "
                    "VALUES ('file_registered_earlier', 'index.html', 0, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                )
            )
        assert "source_path" not in await _artifact_columns(engine)

        full_list = list(migrations.MIGRATION_STATEMENTS)
        added_at = next(i for i, stmt in enumerate(full_list) if "artifacts ADD COLUMN source_path" in stmt)
        # An upgrading user already recorded every migration that preceded the source_path statement.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[:added_at])
        await migrations.run_migrations(engine)
        assert "source_path" not in await _artifact_columns(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        assert (await _artifact_columns(engine))["source_path"] == ("VARCHAR(1024)", 0)
        async with engine.connect() as conn:
            stored = (
                await conn.execute(text("SELECT source_path FROM artifacts WHERE id = 'file_registered_earlier'"))
            ).scalar_one()
        # A file registered earlier has no recorded path; NULL is what the deploy reader falls back from.
        assert stored is None
    finally:
        await engine.dispose()
