"""The server database no longer holds ``procedural_rules``: the table belonged to a model nothing read or wrote.

The rules the agent follows live in the memory store's own file, in a table of the same name with other columns. An
existing server database drops the old table with its indexes when it starts; a new one never creates it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.types import MemoryScope, ProceduralMemory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base

_TABLE = "procedural_rules"
_DROP = f"DROP TABLE IF EXISTS {_TABLE}"
_FULL_INDEXES = list(migrations.INDEX_STATEMENTS)
_TABLE_INDEX_VERSIONS = tuple(i for i, sql in enumerate(_FULL_INDEXES) if _TABLE in sql and sql.startswith("CREATE INDEX"))

# The table, its extra column and its indexes as a release that still mapped the model left them in a database.
_OLD_TABLE = (
    f"CREATE TABLE IF NOT EXISTS {_TABLE} (id VARCHAR(255) NOT NULL, rule_text TEXT NOT NULL, "
    "context VARCHAR(255) NOT NULL, priority INTEGER NOT NULL, is_active BOOLEAN NOT NULL, "
    "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
    "PRIMARY KEY (id))",
    f"CREATE INDEX IF NOT EXISTS ix_{_TABLE}_context ON {_TABLE} (context)",
    *(sql for sql in migrations.MIGRATION_STATEMENTS if _TABLE in sql),
    *(_FULL_INDEXES[version] for version in _TABLE_INDEX_VERSIONS),
)
_STRAY_ROW = f"INSERT INTO {_TABLE} (id, rule_text, context, priority, is_active) VALUES ('stray', 'x', 'general', 0, 1)"


async def _start(engine: AsyncEngine) -> None:
    """The statements ``init_database`` runs once the tables exist, in its order."""
    await migrations.run_migrations(engine)
    await migrations.create_indexes(engine)


async def _objects(engine: AsyncEngine) -> set[tuple[str, str, str]]:
    """Every table, index, trigger and view as (type, name, table)."""
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT type, name, tbl_name FROM sqlite_master"))
        return {(row[0], row[1], row[2]) for row in rows}


async def _user_version(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text("PRAGMA user_version"))).scalar_one())


@pytest.fixture
async def old_release_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    """A database an older release left: the table with its indexes and a stray row, every released statement recorded."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'data.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for statement in _OLD_TABLE:
                await conn.execute(text(statement))
            await conn.execute(text(_STRAY_ROW))
        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _FULL_INDEXES[: _FULL_INDEXES.index(_DROP)])
        await _start(engine)
        yield engine
    finally:
        await engine.dispose()


def test_no_model_maps_the_retired_table() -> None:
    assert _TABLE not in Base.metadata.tables


def test_the_drop_is_an_index_list_statement_that_follows_every_other_statement_on_the_table() -> None:
    # A drop in MIGRATION_STATEMENTS would raise the schema version that older builds refuse to open, and would run
    # before the index statements that still name the table.
    assert not any(_TABLE in sql and sql.startswith("DROP") for sql in migrations.MIGRATION_STATEMENTS)
    assert _FULL_INDEXES.count(_DROP) == 1
    others = [i for i, sql in enumerate(_FULL_INDEXES) if _TABLE in sql and sql != _DROP]
    assert others
    assert _FULL_INDEXES.index(_DROP) > max(others)


@pytest.mark.asyncio
@pytest.mark.parametrize("forgotten", [(), _TABLE_INDEX_VERSIONS], ids=["records_kept", "records_of_its_index_statements_lost"])
async def test_an_upgrading_database_drops_the_table_with_its_indexes_and_nothing_else(
    old_release_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, forgotten: tuple[int, ...]
) -> None:
    engine = old_release_engine
    if forgotten:
        # The statements run again and find the table: the drop that follows them must not have run first.
        async with engine.begin() as conn:
            for version in forgotten:
                await conn.execute(text(f"DELETE FROM _schema_indexes WHERE version = {version}"))
    before = await _objects(engine)
    retired = {obj for obj in before if obj[2] == _TABLE}
    assert {name for _, name, _ in retired} >= {_TABLE, f"ix_{_TABLE}_context"}
    version_before = await _user_version(engine)

    monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _FULL_INDEXES)
    await _start(engine)
    after = await _objects(engine)
    await _start(engine)

    assert after == before - retired
    assert await _objects(engine) == after
    assert await _user_version(engine) == version_before == len(migrations.MIGRATION_STATEMENTS) - 1


@pytest.mark.asyncio
async def test_a_database_whose_table_is_already_gone_starts_all_the_same(
    old_release_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with old_release_engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE {_TABLE}"))

    monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _FULL_INDEXES)
    await _start(old_release_engine)

    assert not {obj for obj in await _objects(old_release_engine) if obj[2] == _TABLE}


@pytest.mark.asyncio
async def test_a_new_database_never_has_the_table_and_starts_twice(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await _start(engine)
        await _start(engine)

        assert not {obj for obj in await _objects(engine) if obj[2] == _TABLE}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_memory_stores_rules_in_its_own_file_are_not_touched(
    old_release_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = SQLiteRelationalStore(str(tmp_path / "memory.db"))
    try:
        for rule_id, action in (("r1", "Reply in English."), ("r2", "Reply in German.")):
            await store.create_rule(
                ProceduralMemory(
                    id=rule_id, content=action, trigger="always", action=action, scope=MemoryScope(primary_namespace="user")
                )
            )
        before = sorted((rule.id, rule.trigger, rule.action) for rule in await store.list_rules(active_only=False))

        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _FULL_INDEXES)
        await _start(old_release_engine)
        after = sorted((rule.id, rule.trigger, rule.action) for rule in await store.list_rules(active_only=False))
    finally:
        await store.close()

    assert len(before) == 2
    assert after == before
