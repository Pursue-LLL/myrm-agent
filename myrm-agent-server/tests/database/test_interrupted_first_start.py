"""A start killed before its baseline committed must not wedge the database for good.

The state tables commit before their baseline rows, so a kill in between leaves them empty next to a schema that
``create_all`` built. Replaying the statement lists against that schema fails on the first statement, on every later
start, and nothing is ever recorded to break the loop.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
from myrm_agent_harness.utils.db.migration_engine import StatefulMigrationEngine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config.settings import settings
from app.database import migrations
from app.database.connection import init_database
from app.database.models import Base
from app.platform_utils import reset_database_engine


class _KilledError(Exception):
    """Stands in for the process dying while the baseline rows are being written."""


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def _die_on_the_second_baseline_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the next baseline stop after its first row, as a killed process would."""
    real_checksum = StatefulMigrationEngine._compute_checksum
    rows_seen = 0

    def checksum(self: StatefulMigrationEngine, sql: str) -> str:
        nonlocal rows_seen
        rows_seen += 1
        if rows_seen == 2:
            raise _KilledError
        return real_checksum(self, sql)

    monkeypatch.setattr(StatefulMigrationEngine, "_compute_checksum", checksum)


async def _row_count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()


async def _user_version(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("PRAGMA user_version"))).scalar_one()


@pytest.mark.parametrize(
    ("start", "state_table", "statement_count"),
    [
        (migrations.run_migrations, "_schema_migrations", lambda: len(migrations.MIGRATION_STATEMENTS)),
        (migrations.create_indexes, "_schema_indexes", lambda: len(migrations.INDEX_STATEMENTS)),
    ],
    ids=["migrations", "indexes"],
)
async def test_a_start_killed_before_its_baseline_committed_is_finished_by_the_next_one(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    start: Callable[[AsyncEngine], Awaitable[None]],
    state_table: str,
    statement_count: Callable[[], int],
) -> None:
    with monkeypatch.context() as killed_start:
        _die_on_the_second_baseline_row(killed_start)
        with pytest.raises(_KilledError):
            await start(engine)
    assert await _row_count(engine, state_table) == 0

    await start(engine)

    assert await _row_count(engine, state_table) == statement_count()


async def test_the_next_start_leaves_the_migrations_recorded_as_a_clean_baseline_would(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as killed_start:
        _die_on_the_second_baseline_row(killed_start)
        with pytest.raises(_KilledError):
            await migrations.run_migrations(engine)

    await migrations.run_migrations(engine)

    assert await _user_version(engine) == len(migrations.MIGRATION_STATEMENTS) - 1
    assert await migrations.has_pending_migrations(engine) is False


@pytest.mark.integration
async def test_init_database_starts_after_a_start_that_was_killed_mid_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.database, "sqlite_path", str(tmp_path / "server.db"))
    await reset_database_engine()
    try:
        with monkeypatch.context() as killed_start:
            _die_on_the_second_baseline_row(killed_start)
            with pytest.raises(_KilledError):
                await init_database()

        await init_database()
    finally:
        await reset_database_engine()
