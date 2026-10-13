"""Existing databases lose the unused ``message_filter_config.pii_mode`` column through the append-only migration list."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.database import migrations
from app.database.models import Base, MessageFilterConfig

_DROP_PII_MODE = "ALTER TABLE message_filter_config DROP COLUMN pii_mode"

# The table as a database created before the column was removed holds it: NOT NULL, no server default.
_LEGACY_TABLE = """
CREATE TABLE message_filter_config (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    enabled BOOLEAN NOT NULL,
    pii_mode VARCHAR(50) NOT NULL,
    whitelist_api_keys JSON NOT NULL,
    audit_enabled BOOLEAN NOT NULL,
    updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    updated_by VARCHAR(255)
)
"""


async def _columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("PRAGMA table_info(message_filter_config)"))
        return {row[1] for row in rows}


async def _insert_default_config(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        session.add(MessageFilterConfig())
        await session.commit()


@pytest.mark.asyncio
async def test_run_migrations_drops_pii_mode_and_keeps_the_stored_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("DROP TABLE message_filter_config"))
            await conn.execute(text(_LEGACY_TABLE))
            await conn.execute(
                text(
                    "INSERT INTO message_filter_config (enabled, pii_mode, whitelist_api_keys, audit_enabled) "
                    "VALUES (0, 'block', '[\"sk-keep\"]', 1)"
                )
            )

        full_list = list(migrations.MIGRATION_STATEMENTS)
        drop_index = full_list.index(_DROP_PII_MODE)
        # An upgrading user already recorded every migration that preceded the drop.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[:drop_index])
        await migrations.run_migrations(engine)
        assert "pii_mode" in await _columns(engine)
        with pytest.raises(IntegrityError):
            await _insert_default_config(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        assert "pii_mode" not in await _columns(engine)
        async with engine.connect() as conn:
            kept = (await conn.execute(text("SELECT enabled, whitelist_api_keys FROM message_filter_config"))).all()
        assert [(row[0], row[1]) for row in kept] == [(0, '["sk-keep"]')]
        await _insert_default_config(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_migrations_accepts_a_database_that_never_had_pii_mode(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await migrations.run_migrations(engine)
        await migrations.run_migrations(engine)

        assert "pii_mode" not in await _columns(engine)
        await _insert_default_config(engine)
    finally:
        await engine.dispose()
