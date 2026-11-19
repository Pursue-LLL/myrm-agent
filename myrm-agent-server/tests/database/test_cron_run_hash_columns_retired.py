"""Existing databases lose the two cron run hash columns; fresh databases never create them."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.database import migrations
from app.database.models import Base, CronJobModel, CronRunModel

_HASH_COLUMNS = ("integrity_hash", "prev_hash")
_ADDS = tuple(f"ALTER TABLE cron_runs ADD COLUMN {column} VARCHAR(64)" for column in _HASH_COLUMNS)
_DROPS = tuple(f"ALTER TABLE cron_runs DROP COLUMN {column}" for column in _HASH_COLUMNS)


async def _run_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return {row[1] for row in await conn.execute(text("PRAGMA table_info(cron_runs)"))}


def test_each_drop_runs_after_the_statement_that_added_its_column() -> None:
    # Both statements share one list and one ledger, so the order in the list is the order of execution.
    statements = migrations.MIGRATION_STATEMENTS
    for add, drop in zip(_ADDS, _DROPS, strict=True):
        assert statements.index(add) < statements.index(drop)


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_hash_columns_and_keeps_its_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrading.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # The shape of an upgrading database: the table still carries the columns the model no longer maps.
            for add in _ADDS:
                await conn.execute(text(add))

        now = datetime.now(UTC)
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            session.add(CronJobModel(id="job-1", name="Kept job", job_type="shell", schedule={"kind": "interval"}))
            await session.flush()
            session.add(CronRunModel(id="run-1", job_id="job-1", started_at=now, finished_at=now, duration_ms=5, status="ok"))
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE cron_runs SET integrity_hash = 'h1', prev_hash = 'h0' WHERE id = 'run-1'"))

        full_list = list(migrations.MIGRATION_STATEMENTS)
        # The upgrading database already recorded every statement that precedes the drops.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[: full_list.index(_DROPS[0])])
        await migrations.run_migrations(engine)
        assert set(_HASH_COLUMNS) <= await _run_columns(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        assert not set(_HASH_COLUMNS) & await _run_columns(engine)
        async with engine.connect() as conn:
            run = (await conn.execute(text("SELECT id, job_id, status, duration_ms FROM cron_runs"))).one()
        assert tuple(run) == ("run-1", "job-1", "ok", 5)
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

        assert not set(_HASH_COLUMNS) & await _run_columns(engine)
        assert not set(_HASH_COLUMNS) & set(CronRunModel.__table__.columns.keys())
    finally:
        await engine.dispose()
