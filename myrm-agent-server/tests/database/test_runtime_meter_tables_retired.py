"""Existing databases drop the retired runtime-meter tables; fresh databases never create them."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base

_METER_TABLES = ("search_quota_records", "browser_runtime_records", "sandbox_workload_records")
_FIRST_DROP = "DROP TABLE IF EXISTS search_quota_records"

# The shape of an upgrading database: the three ledgers carry their own indexes and no foreign key links them.
_UPGRADING_DB_DDL = """
CREATE TABLE search_quota_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider VARCHAR(32) NOT NULL,
    year_month VARCHAR(7) NOT NULL,
    used_count INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX ix_search_quota_provider_month ON search_quota_records(provider, year_month);
CREATE TABLE browser_runtime_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month VARCHAR(7) NOT NULL,
    session_id VARCHAR(128)
);
CREATE INDEX ix_browser_runtime_year_month ON browser_runtime_records(year_month);
CREATE TABLE sandbox_workload_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month VARCHAR(7) NOT NULL,
    workload_type VARCHAR(32) NOT NULL DEFAULT 'code_sandbox'
);
CREATE INDEX ix_sandbox_workload_year_month ON sandbox_workload_records(year_month);
"""

_SEED_ROWS = (
    "INSERT INTO search_quota_records (provider, year_month, used_count) VALUES ('tavily', '2026-10', 3)",
    "INSERT INTO browser_runtime_records (year_month, session_id) VALUES ('2026-10', 's1')",
    "INSERT INTO sandbox_workload_records (year_month) VALUES ('2026-10')",
    "INSERT INTO user_configs (id, config_key, config_value, version, last_device_id, is_encrypted) VALUES ('u1', 'k', '{}', '1', 'd', 0)",
)


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        return {row[0] for row in rows}


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_meter_tables_and_keeps_everything_else(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrading.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for statement in filter(None, (part.strip() for part in _UPGRADING_DB_DDL.split(";"))):
                await conn.execute(text(statement))
            for statement in _SEED_ROWS:
                await conn.execute(text(statement))

        full_list = list(migrations.MIGRATION_STATEMENTS)
        # The upgrading user already recorded every migration that preceded the meter-table drops.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[: full_list.index(_FIRST_DROP)])
        await migrations.run_migrations(engine)
        assert set(_METER_TABLES) <= await _tables(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        assert not set(_METER_TABLES) & await _tables(engine)
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

        assert not set(_METER_TABLES) & await _tables(engine)
        assert not set(_METER_TABLES) & set(Base.metadata.tables)
    finally:
        await engine.dispose()
