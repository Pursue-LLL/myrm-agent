"""Existing databases drop the message-filter admin tables; fresh databases never create them."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base

_ADMIN_TABLES = (
    "message_filter_config",
    "message_filter_rules",
    "message_filter_audit",
    "message_filter_config_history",
)
_DROP_PII_MODE = "ALTER TABLE message_filter_config DROP COLUMN pii_mode"

# The layout of an upgrading database: `message_filter_config` still carries the `pii_mode` column.
_UPGRADING_DB_DDL = """
CREATE TABLE message_filter_config (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    enabled BOOLEAN NOT NULL,
    pii_mode VARCHAR(50) NOT NULL,
    whitelist_api_keys JSON NOT NULL,
    audit_enabled BOOLEAN NOT NULL
);
CREATE TABLE message_filter_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(255) NOT NULL);
CREATE TABLE message_filter_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, filter_type VARCHAR(100) NOT NULL);
CREATE INDEX ix_message_filter_audit_filter_type ON message_filter_audit(filter_type);
CREATE TABLE message_filter_config_history (id INTEGER PRIMARY KEY AUTOINCREMENT, version INTEGER NOT NULL);
"""


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        return {row[0] for row in rows}


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_admin_tables_and_keeps_everything_else(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrading.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for statement in filter(None, (part.strip() for part in _UPGRADING_DB_DDL.split(";"))):
                await conn.execute(text(statement))
            await conn.execute(
                text(
                    "INSERT INTO message_filter_config (enabled, pii_mode, whitelist_api_keys, audit_enabled) VALUES (0, 'block', '[]', 1)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO user_configs (id, config_key, config_value, version, last_device_id, is_encrypted) VALUES ('u1', 'k', '{}', '1', 'd', 0)"
                )
            )

        full_list = list(migrations.MIGRATION_STATEMENTS)
        # The upgrading user already recorded every migration that preceded the pii_mode drop.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[: full_list.index(_DROP_PII_MODE)])
        await migrations.run_migrations(engine)
        assert set(_ADMIN_TABLES) <= await _tables(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        assert not set(_ADMIN_TABLES) & await _tables(engine)
        async with engine.connect() as conn:
            assert (await conn.execute(text("SELECT COUNT(*) FROM user_configs"))).scalar_one() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_new_database_never_creates_them_and_migrations_stay_idempotent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await migrations.run_migrations(engine)
        await migrations.run_migrations(engine)

        assert not set(_ADMIN_TABLES) & await _tables(engine)
        assert not set(_ADMIN_TABLES) & set(Base.metadata.tables)
    finally:
        await engine.dispose()
