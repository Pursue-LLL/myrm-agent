"""Existing databases must gain ``chats.tags`` through the append-only migration list."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base


async def _chat_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("PRAGMA table_info(chats)"))
        return {row[1] for row in rows}


@pytest.mark.asyncio
async def test_run_migrations_adds_tags_column_to_existing_chats_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # An upgrading database still carries the message_filter_config table that a later migration alters.
            await conn.execute(text("CREATE TABLE message_filter_config (id INTEGER PRIMARY KEY, pii_mode VARCHAR(50))"))
            await conn.execute(text("ALTER TABLE chats DROP COLUMN tags"))
        assert "tags" not in await _chat_columns(engine)

        full_list = list(migrations.MIGRATION_STATEMENTS)
        tags_index = next(i for i, stmt in enumerate(full_list) if "chats ADD COLUMN tags" in stmt)
        # An upgrading user already recorded every migration that preceded the tags statement.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[:tags_index])
        await migrations.run_migrations(engine)
        assert "tags" not in await _chat_columns(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        assert "tags" in await _chat_columns(engine)
    finally:
        await engine.dispose()
