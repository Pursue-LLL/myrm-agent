"""Existing databases lose the ``agents`` governance columns; fresh ones never keep them and the migrations stay idempotent."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.database import migrations
from app.database.models import Agent, Base

_COLUMNS = ("responsibility_scope", "owner_label", "acceptance_criteria")
_RETIRED = frozenset(_COLUMNS)
_ADDS = (
    "ALTER TABLE agents ADD COLUMN responsibility_scope TEXT",
    "ALTER TABLE agents ADD COLUMN owner_label VARCHAR(100)",
    "ALTER TABLE agents ADD COLUMN acceptance_criteria JSON",
)
_DROPS = tuple(f"ALTER TABLE agents DROP COLUMN {column}" for column in _COLUMNS)
_FULL_LIST = list(migrations.MIGRATION_STATEMENTS)
# An upgrading database already recorded every statement that precedes the first drop.
_RELEASED = _FULL_LIST[: _FULL_LIST.index(_DROPS[0])]


async def _agent_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return {row[1] for row in await conn.execute(text("PRAGMA table_info(agents)"))}


def test_every_drop_runs_after_the_statement_that_added_its_column() -> None:
    # Both statements share one list and one ledger, so the order in the list is the order of execution.
    for add, drop in zip(_ADDS, _DROPS, strict=True):
        assert _FULL_LIST.index(add) < _FULL_LIST.index(drop)


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_columns_and_keeps_its_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrading.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # The shape of an upgrading database: the table still carries the columns the models no longer map.
            for add in _ADDS:
                await conn.execute(text(add))
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _RELEASED)
        await migrations.run_migrations(engine)
        columns_before = await _agent_columns(engine)
        assert _RETIRED <= columns_before

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(Agent(id="legacy-agent", name="Kept name", description="Kept description"))
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE agents SET responsibility_scope = 'Owns billing', owner_label = 'Finance', "
                    "acceptance_criteria = '[\"invoice sent\"]' WHERE id = 'legacy-agent'"
                )
            )

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _FULL_LIST)
        await migrations.run_migrations(engine)

        columns_after = await _agent_columns(engine)
        assert not _RETIRED & columns_after
        assert columns_before - _RETIRED <= columns_after
        async with sessions() as session:
            agent = (await session.execute(select(Agent).where(Agent.id == "legacy-agent"))).scalar_one()
        assert (agent.name, agent.description) == ("Kept name", "Kept description")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_database_that_never_had_the_columns_skips_the_drops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'never_had_them.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _RELEASED)
        await migrations.run_migrations(engine)
        assert not _RETIRED & await _agent_columns(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _FULL_LIST)
        await migrations.run_migrations(engine)

        assert not _RETIRED & await _agent_columns(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_new_database_never_keeps_the_columns_and_migrations_stay_idempotent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await migrations.run_migrations(engine)
        await migrations.run_migrations(engine)

        assert not _RETIRED & await _agent_columns(engine)
        assert not _RETIRED & {column.name for column in Agent.__table__.columns}
    finally:
        await engine.dispose()
