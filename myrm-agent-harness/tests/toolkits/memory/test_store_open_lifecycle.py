"""A lazily opened memory store never keeps a connection that lacks its hardening or its tables.

The graph, relational and preference-facet stores open their SQLite connection on first use. However that setup ends
(a statement fails, or the caller gives up on the open), the next call has to start over and end up with a fully
hardened connection and the tables, and a ``close()`` that overlaps an open has to leave no connection behind. Every
case runs on a new database file (first install) and on an existing one (every start after that).
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable, Generator, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

import aiosqlite
import pytest
import pytest_asyncio

from myrm_agent_harness.toolkits.memory.graph.exceptions import GraphConnectionError
from myrm_agent_harness.toolkits.memory.graph.sqlite_store import SQLiteGraphStore
from myrm_agent_harness.toolkits.memory.relational.exceptions import (
    CorruptedMemoryIndexError,
    RelationalConnectionError,
)
from myrm_agent_harness.toolkits.memory.relational.sqlite_store import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.strategies.preference_stability_store import SQLitePreferenceFacetStore

SETTINGS = ("foreign_keys", "secure_delete", "cell_size_check", "journal_mode", "busy_timeout", "synchronous")
# Runs after the journal mode is set and before the last settings, so a fault on it leaves a half hardened connection.
HARDENING_STATEMENT = "PRAGMA secure_delete"
FAULT = "injected fault"
STAGES = ("harden", "tables")
SETTLE_STEPS = 5
TIMEOUT_SECONDS = 20


class Store(Protocol):
    async def close(self) -> None: ...


@dataclass(frozen=True, repr=False)
class StoreCase:
    """What the lifecycle tests need to know about one store."""

    name: str
    make: Callable[[Path], Store]
    use: Callable[[Store], Awaitable[object]]  # the first call, which opens the connection
    connection: Callable[[Store], aiosqlite.Connection | None]  # the connection the store keeps
    table_statement: str  # a table-creating statement that runs on every open
    tables: tuple[str, ...]
    error: type[Exception]  # what a failing statement surfaces as
    messages: dict[str, str]  # stage -> pattern of that error's message
    ready: Callable[[Store], bool] = field(default=lambda _store: True)  # the store's own record of its setup

    def __repr__(self) -> str:
        return self.name

    def statement(self, stage: str) -> str:
        return HARDENING_STATEMENT if stage == "harden" else self.table_statement


GRAPH = StoreCase(
    name="graph",
    make=lambda path: SQLiteGraphStore(str(path)),
    use=lambda store: cast("SQLiteGraphStore", store).get_stats(),
    connection=lambda store: cast("SQLiteGraphStore", store)._connection,
    table_statement="CREATE TABLE IF NOT EXISTS graph_relationships",
    tables=("graph_nodes", "graph_relationships"),
    error=GraphConnectionError,
    messages={
        "harden": f"^Failed to connect to SQLite: {FAULT}$",
        "tables": f"^Failed to connect to SQLite: Failed to initialize tables: {FAULT}$",
    },
)
RELATIONAL = StoreCase(
    name="relational",
    make=lambda path: SQLiteRelationalStore(str(path)),
    use=lambda store: cast("SQLiteRelationalStore", store).count_rules(),
    connection=lambda store: cast("SQLiteRelationalStore", store)._connection,
    table_statement="CREATE TABLE IF NOT EXISTS procedural_rules",
    tables=("profiles", "procedural_rules", "pending_records"),
    error=RelationalConnectionError,
    messages={
        "harden": f"^Failed to connect: {FAULT}$",
        "tables": f"^Failed to connect: Failed to initialize tables: {FAULT}$",
    },
    ready=lambda store: cast("SQLiteRelationalStore", store)._fts5_supported,
)
FACET = StoreCase(
    name="facet",
    make=lambda path: SQLitePreferenceFacetStore(str(path)),
    use=lambda store: cast("SQLitePreferenceFacetStore", store).list_all(),
    connection=lambda store: cast("SQLitePreferenceFacetStore", store)._conn,
    table_statement="CREATE TABLE IF NOT EXISTS preference_facets",
    tables=("preference_facets",),
    error=sqlite3.OperationalError,
    messages={"harden": f"^{FAULT}$", "tables": f"^{FAULT}$"},
)
CASES = (GRAPH, RELATIONAL, FACET)

all_cases = pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
all_stages = pytest.mark.parametrize("stage", STAGES)
all_databases = pytest.mark.parametrize("existing", [False, True], ids=["new_db", "existing_db"])


class Faults:
    """Fails or stalls the next statement that starts with a prefix, on any connection, and remembers every connection
    it saw so a test can check that none of them was left open."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.connections: list[aiosqlite.Connection] = []
        self.reached = asyncio.Event()
        self._prefix: str | None = None
        self._stall = False
        self._once = True
        self._message = FAULT
        real_execute = aiosqlite.Connection.execute

        def execute(connection: aiosqlite.Connection, sql: str, parameters: Iterable[object] | None = None) -> object:
            self.remember(connection)
            if self._prefix is not None and sql.lstrip().startswith(self._prefix):
                if self._once:
                    self._prefix = None
                return self._fault()
            return real_execute(connection, sql, parameters)

        monkeypatch.setattr(aiosqlite.Connection, "execute", execute)

    def remember(self, connection: aiosqlite.Connection) -> None:
        if connection not in self.connections:
            self.connections.append(connection)

    async def _fault(self) -> None:
        if self._stall:
            self.reached.set()
            await asyncio.Event().wait()
        raise sqlite3.OperationalError(self._message)

    def raise_on(self, prefix: str, *, once: bool = True, message: str = FAULT) -> None:
        self._prefix, self._stall, self._once, self._message = prefix, False, once, message

    def stall_on(self, prefix: str) -> None:
        self._prefix, self._stall, self._once = prefix, True, True

    def disarm(self) -> None:
        self._prefix = None

    def hold_connects(self, monkeypatch: pytest.MonkeyPatch) -> tuple[asyncio.Event, asyncio.Event]:
        """Make every connection open wait for the returned release event; the first event is set once one waits."""
        started, release = asyncio.Event(), asyncio.Event()
        real_connect = aiosqlite.connect
        faults = self

        class HeldOpen:
            def __init__(self, database: str) -> None:
                self._real = real_connect(database)

            def __await__(self) -> Generator[object, None, aiosqlite.Connection]:
                return self._open().__await__()

            async def _open(self) -> aiosqlite.Connection:
                started.set()
                await release.wait()
                connection = await self._real
                faults.remember(connection)
                return connection

        monkeypatch.setattr(aiosqlite, "connect", lambda database, **_kwargs: HeldOpen(str(database)))
        return started, release


@pytest_asyncio.fixture
async def faults(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Faults]:
    injected = Faults(monkeypatch)
    yield injected
    # A connection the code under test left open pins a non-daemon worker thread, which would keep the test process alive.
    injected.disarm()
    for connection in injected.connections:
        with contextlib.suppress(Exception):
            await connection.close()


async def settings_of(connection: aiosqlite.Connection) -> dict[str, object]:
    values: dict[str, object] = {}
    for name in SETTINGS:
        async with connection.execute(f"PRAGMA {name}") as cursor:
            row = await cursor.fetchone()
        values[name] = row[0] if row else None
    return values


async def table_names(connection: aiosqlite.Connection) -> set[str]:
    async with connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'") as cursor:
        return {str(row[0]) for row in await cursor.fetchall()}


async def assert_closed(connection: aiosqlite.Connection) -> None:
    """aiosqlite refuses every statement on a closed connection with a ``ValueError``."""
    with pytest.raises(ValueError):
        await connection.execute("SELECT 1")


async def healthy_settings(case: StoreCase, directory: Path) -> dict[str, object]:
    """The settings a connection of this store has when nothing goes wrong."""
    store = case.make(directory / "control.db")
    try:
        await case.use(store)
        connection = case.connection(store)
        assert connection is not None
        return await settings_of(connection)
    finally:
        await store.close()


async def database(case: StoreCase, directory: Path, *, existing: bool) -> Path:
    """The path of a database file that either does not exist yet or was created by an earlier run."""
    path = directory / "memory.db"
    if existing:
        earlier = case.make(path)
        try:
            await case.use(earlier)
        finally:
            await earlier.close()
    return path


async def settle() -> None:
    for _ in range(SETTLE_STEPS):
        await asyncio.sleep(0)


async def assert_next_call_starts_over(
    case: StoreCase, store: Store, faults: Faults, expected: dict[str, object]
) -> None:
    """The next call works on a connection hardened like a healthy one, with the tables, and no failed one stayed open."""
    faults.disarm()
    await case.use(store)
    live = case.connection(store)
    assert live is not None
    assert await settings_of(live) == expected
    assert set(case.tables) <= await table_names(live)
    assert case.ready(store)
    for connection in faults.connections:
        if connection is not live:
            await assert_closed(connection)


@all_cases
async def test_a_healthy_connection_is_hardened(case: StoreCase, tmp_path: Path, faults: Faults) -> None:
    settings = await healthy_settings(case, tmp_path)

    assert settings["foreign_keys"] == 1
    assert settings["cell_size_check"] == 1
    assert settings["secure_delete"] != 0
    assert str(settings["journal_mode"]).lower() == "wal"
    assert settings["busy_timeout"] == 5000


@all_databases
@all_stages
@all_cases
async def test_a_failed_open_keeps_nothing_and_the_next_call_starts_over(
    case: StoreCase, stage: str, existing: bool, tmp_path: Path, faults: Faults
) -> None:
    async with asyncio.timeout(TIMEOUT_SECONDS):
        expected = await healthy_settings(case, tmp_path)
        store = case.make(await database(case, tmp_path, existing=existing))
        faults.raise_on(case.statement(stage))

        with pytest.raises(case.error, match=case.messages[stage]):
            await case.use(store)
        assert case.connection(store) is None

        await assert_next_call_starts_over(case, store, faults, expected)
        await store.close()


@all_databases
@all_stages
@all_cases
async def test_a_cancelled_open_keeps_nothing_and_the_next_call_starts_over(
    case: StoreCase, stage: str, existing: bool, tmp_path: Path, faults: Faults
) -> None:
    async with asyncio.timeout(TIMEOUT_SECONDS):
        expected = await healthy_settings(case, tmp_path)
        store = case.make(await database(case, tmp_path, existing=existing))
        faults.stall_on(case.statement(stage))

        opening = asyncio.create_task(case.use(store))
        await faults.reached.wait()
        opening.cancel()
        with pytest.raises(asyncio.CancelledError):
            await opening
        assert case.connection(store) is None

        await assert_next_call_starts_over(case, store, faults, expected)
        await store.close()


@all_databases
@all_stages
@all_cases
async def test_a_call_queued_behind_a_cancelled_open_gets_a_complete_connection(
    case: StoreCase, stage: str, existing: bool, tmp_path: Path, faults: Faults
) -> None:
    async with asyncio.timeout(TIMEOUT_SECONDS):
        expected = await healthy_settings(case, tmp_path)
        store = case.make(await database(case, tmp_path, existing=existing))
        faults.stall_on(case.statement(stage))

        first = asyncio.create_task(case.use(store))
        await faults.reached.wait()
        second = asyncio.create_task(case.use(store))
        await settle()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await second

        await assert_next_call_starts_over(case, store, faults, expected)
        await store.close()


@all_stages
@all_cases
async def test_every_call_retries_a_persistent_failure_and_keeps_no_connection(
    case: StoreCase, stage: str, tmp_path: Path, faults: Faults
) -> None:
    async with asyncio.timeout(TIMEOUT_SECONDS):
        expected = await healthy_settings(case, tmp_path)
        store = case.make(tmp_path / "memory.db")
        faults.raise_on(case.statement(stage), once=False)

        for _ in range(3):
            with pytest.raises(case.error, match=case.messages[stage]):
                await case.use(store)
            assert case.connection(store) is None

        await assert_next_call_starts_over(case, store, faults, expected)
        await store.close()


@all_databases
@all_cases
async def test_closing_while_a_store_opens_leaves_no_connection_behind(
    case: StoreCase, existing: bool, tmp_path: Path, faults: Faults, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with asyncio.timeout(TIMEOUT_SECONDS):
        store = case.make(await database(case, tmp_path, existing=existing))
        opening_started, release = faults.hold_connects(monkeypatch)

        opening = asyncio.create_task(case.use(store))
        await opening_started.wait()
        closing = asyncio.create_task(store.close())
        await settle()
        release.set()
        await asyncio.gather(opening, closing, return_exceptions=True)

        assert case.connection(store) is None
        for connection in faults.connections:
            await assert_closed(connection)


@all_stages
async def test_a_failure_that_reads_as_corruption_is_reported_as_corruption(
    stage: str, tmp_path: Path, faults: Faults
) -> None:
    store = RELATIONAL.make(tmp_path / "memory.db")
    faults.raise_on(RELATIONAL.statement(stage), message="database disk image is malformed")

    with pytest.raises(CorruptedMemoryIndexError, match="malformed"):
        await RELATIONAL.use(store)

    assert RELATIONAL.connection(store) is None
    for connection in faults.connections:
        await assert_closed(connection)
    await store.close()
