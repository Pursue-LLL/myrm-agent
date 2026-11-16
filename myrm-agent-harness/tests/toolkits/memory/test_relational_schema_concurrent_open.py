"""Stores that open one older database at the same moment all open it.

After an upgrade, several managers of one process (or several processes) can open the same memory database for the
first time together. SQLite has no ``IF NOT EXISTS`` for ``ADD COLUMN`` or ``DROP COLUMN``, so a store that listed the
columns before another store changed them has to take that change as done instead of failing on it.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import cast

import aiosqlite
import pytest
from aiosqlite.context import Result

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore, _schema
from myrm_agent_harness.toolkits.memory.relational.exceptions import RelationalConnectionError
from tests.support.relational_records import make_rule

# Columns an older release wrote on every rule, and rule/approval-queue columns that release did not have yet.
DEAD_RULE_COLUMNS = ("priority", "trigger_keywords")
MISSING_RULE_COLUMNS = ("access_count", "last_accessed_at", "expected_valid_days")
MISSING_PENDING_COLUMNS = ("target_memory_id", "target_content")
TRIALS = 6


def columns_of(path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


async def current_database(path: Path) -> None:
    """A database in the current layout holding one rule."""
    store = SQLiteRelationalStore(str(path))
    try:
        await store.create_rule(make_rule("reply style", "Reply in English."))
    finally:
        await store.close()


def make_old(path: Path) -> None:
    """Turn a current database into one an older release wrote: dead rule columns, and columns it lacked."""
    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE procedural_rules ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
        connection.execute("ALTER TABLE procedural_rules ADD COLUMN trigger_keywords TEXT")
        for column in MISSING_RULE_COLUMNS:
            connection.execute(f"ALTER TABLE procedural_rules DROP COLUMN {column}")
        for column in MISSING_PENDING_COLUMNS:
            connection.execute(f"ALTER TABLE pending_records DROP COLUMN {column}")
        connection.commit()
    finally:
        connection.close()


def assert_current_layout(path: Path) -> None:
    rule_columns = columns_of(path, "procedural_rules")
    assert not set(DEAD_RULE_COLUMNS) & rule_columns
    assert set(MISSING_RULE_COLUMNS) <= rule_columns
    assert set(MISSING_PENDING_COLUMNS) <= columns_of(path, "pending_records")


class RacingConnection:
    """A connection that lets another connection apply a step right before this one's statement for it runs.

    That is the interleaving of two stores opening one database: both listed the columns, the other one was first.
    """

    def __init__(self, connection: aiosqlite.Connection, before: Callable[[str], None]) -> None:
        self._connection = connection
        self._before = before

    def execute(self, sql: str, parameters: Iterable[object] | None = None) -> Result[aiosqlite.Cursor]:
        self._before(sql)
        return self._connection.execute(sql, parameters)

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)


async def init_against_racing_neighbour(path: Path, step: str) -> None:
    """Run the schema bootstrap on ``path``; just before it issues a statement starting with ``step``, another
    connection runs that same statement."""

    def neighbour(sql: str) -> None:
        if sql.startswith(step):
            other = sqlite3.connect(path)
            try:
                other.execute(sql)
                other.commit()
            finally:
                other.close()

    connection = await aiosqlite.connect(str(path))
    try:
        await _schema.init_relational_schema(cast("aiosqlite.Connection", RacingConnection(connection, neighbour)))
    finally:
        await connection.close()


@pytest.mark.parametrize("openers", [2, 4])
async def test_stores_opening_an_older_database_together_all_open_it(tmp_path: Path, openers: int) -> None:
    for trial in range(TRIALS):
        path = tmp_path / f"memory_{trial}.db"
        await current_database(path)
        make_old(path)

        stores = [SQLiteRelationalStore(str(path)) for _ in range(openers)]
        try:
            counts = await asyncio.gather(*(store.count_rules() for store in stores), return_exceptions=True)
        finally:
            for store in stores:
                await store.close()

        assert counts == [1] * openers, f"trial {trial}"
        assert_current_layout(path)


@pytest.mark.parametrize("column", DEAD_RULE_COLUMNS)
async def test_a_dead_column_another_store_dropped_first_is_not_an_error(tmp_path: Path, column: str) -> None:
    path = tmp_path / "memory.db"
    await current_database(path)
    make_old(path)

    await init_against_racing_neighbour(path, f"ALTER TABLE procedural_rules DROP COLUMN {column}")

    assert_current_layout(path)


@pytest.mark.parametrize(
    ("table", "column"),
    [("procedural_rules", "expected_valid_days"), ("pending_records", "target_content")],
)
async def test_a_column_another_store_added_first_is_not_an_error(tmp_path: Path, table: str, column: str) -> None:
    path = tmp_path / "memory.db"
    await current_database(path)
    make_old(path)

    await init_against_racing_neighbour(path, f"ALTER TABLE {table} ADD COLUMN {column}")

    assert_current_layout(path)


async def test_a_column_step_that_fails_for_another_reason_still_fails(tmp_path: Path) -> None:
    """An index on the column keeps SQLite from dropping it: the column is still there, so the failure surfaces."""
    path = tmp_path / "memory.db"
    await current_database(path)
    make_old(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE INDEX idx_rules_priority ON procedural_rules(priority)")
        connection.commit()
    finally:
        connection.close()

    store = SQLiteRelationalStore(str(path))
    try:
        with pytest.raises(RelationalConnectionError, match="priority"):
            await store.count_rules()
    finally:
        await store.close()

    assert "priority" in columns_of(path, "procedural_rules")
