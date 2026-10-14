"""Existing databases drop the batch-optimization tables; fresh databases never create them."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base

_BATCH_TABLES = ("batch_audit_logs", "batch_optimization_tasks")
_FIRST_DROP = "DROP TABLE IF EXISTS batch_audit_logs"

# The shape of an upgrading database: both tables carry their own indexes and no foreign key links them.
_UPGRADING_DB_DDL = """
CREATE TABLE batch_optimization_tasks (
    batch_id VARCHAR(255) PRIMARY KEY,
    skill_ids JSON NOT NULL,
    status VARCHAR(50) NOT NULL
);
CREATE INDEX ix_batch_optimization_tasks_status ON batch_optimization_tasks(status);
CREATE TABLE batch_audit_logs (
    log_id VARCHAR(255) PRIMARY KEY,
    batch_id VARCHAR(255) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    details JSON NOT NULL
);
CREATE INDEX ix_batch_audit_logs_batch_id ON batch_audit_logs(batch_id);
"""


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        return {row[0] for row in rows}


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_batch_tables_and_keeps_everything_else(
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
                text("INSERT INTO batch_optimization_tasks (batch_id, skill_ids, status) VALUES ('b1', '[]', 'completed')")
            )
            await conn.execute(
                text(
                    "INSERT INTO batch_audit_logs (log_id, batch_id, operation, status, details) VALUES ('l1', 'b1', 'rollback', 'ok', '{}')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO user_configs (id, config_key, config_value, version, last_device_id, is_encrypted) VALUES ('u1', 'k', '{}', '1', 'd', 0)"
                )
            )

        full_list = list(migrations.MIGRATION_STATEMENTS)
        # The upgrading user already recorded every migration that preceded the batch-table drops.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[: full_list.index(_FIRST_DROP)])
        await migrations.run_migrations(engine)
        assert set(_BATCH_TABLES) <= await _tables(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        assert not set(_BATCH_TABLES) & await _tables(engine)
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

        assert not set(_BATCH_TABLES) & await _tables(engine)
        assert not set(_BATCH_TABLES) & set(Base.metadata.tables)
    finally:
        await engine.dispose()
