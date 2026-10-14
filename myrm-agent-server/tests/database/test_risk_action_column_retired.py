"""Existing databases lose the ``action`` columns of the risk tables; fresh databases never have them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base

_FULL_LIST = list(migrations.MIGRATION_STATEMENTS)
_FIRST = _FULL_LIST.index("UPDATE risk_rules SET is_enabled = 0 WHERE action != 'block'")

# The shape of an upgrading database: both tables carried a single-valued ``action`` column.
_ADD_ACTION_COLUMNS = (
    "ALTER TABLE risk_rules ADD COLUMN action VARCHAR(50) NOT NULL DEFAULT 'block'",
    "ALTER TABLE risk_hits ADD COLUMN action VARCHAR(50) NOT NULL DEFAULT 'block'",
)
_SUMMARIES = ["sk-proj-abc123", "13812345678", "", "chars:3-9", "(matching timed out)"]


async def _columns(engine: AsyncEngine, table: str) -> set[str]:
    async with engine.connect() as conn:
        return {row[1] for row in await conn.execute(text(f"PRAGMA table_info({table})"))}


@pytest.fixture
async def upgrading_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    """A database that recorded every migration before the ``action`` ones and still has the columns."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrading.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for statement in _ADD_ACTION_COLUMNS:
                await conn.execute(text(statement))
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _FULL_LIST[:_FIRST])
        await migrations.run_migrations(engine)
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_columns_and_keeps_what_the_user_set(
    upgrading_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with upgrading_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO risk_rules (rule_id, display_name, pattern, severity, category, is_enabled, is_builtin, "
                "sort_order, action) VALUES "
                "('non-block', 'N', 'x', 'low', 'custom', 1, 0, 0, 'allow'), "
                "('current', 'C', 'y', 'low', 'custom', 1, 0, 0, 'block')"
            )
        )
        for summary in _SUMMARIES:
            await conn.execute(
                text(
                    "INSERT INTO risk_hits (trace_id, rule_id, rule_name, severity, match_summary, action) "
                    "VALUES ('t', 'r', 'R', 'high', :summary, 'block')"
                ),
                {"summary": summary},
            )

    monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _FULL_LIST)
    await migrations.run_migrations(upgrading_engine)

    assert "action" not in await _columns(upgrading_engine, "risk_rules")
    assert "action" not in await _columns(upgrading_engine, "risk_hits")
    async with upgrading_engine.connect() as conn:
        rules = dict((await conn.execute(text("SELECT rule_id, is_enabled FROM risk_rules"))).all())
        summaries = (await conn.execute(text("SELECT match_summary FROM risk_hits ORDER BY id"))).scalars().all()
    assert rules == {"non-block": 0, "current": 1}
    assert summaries == ["", "", "", "chars:3-9", "(matching timed out)"]


@pytest.mark.asyncio
async def test_a_new_database_never_has_the_columns_and_migrations_stay_idempotent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await migrations.run_migrations(engine)
        await migrations.run_migrations(engine)

        assert "action" not in await _columns(engine, "risk_rules")
        assert "action" not in await _columns(engine, "risk_hits")
    finally:
        await engine.dispose()
