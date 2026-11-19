"""A file SQLite database that runs the production transaction policy, for tests of read-then-write units.

[INPUT]
- app.database.factory::register_sqlite_transaction_events (POS: the deferred-read / immediate-write policy)
- app.database.models::Base (POS: ORM metadata of every table)

[OUTPUT]
- policy_database: build the schema on a policy-running database that ``get_session()`` then hands out
- hold_write_lock: a writer that keeps the write lock, uncommitted, until the caller lets go
- PolicyDb.unit_waits_or_has_read / wait_until: observe that a unit queued for the write lock or already holds a read snapshot
- run_while_another_writer_commits: run a unit that another writer commits in front of, and wait for it

[POS]
The plain ``sqlite+aiosqlite`` engines most fixtures use do not run the policy, so a write lost to SQLITE_BUSY_SNAPSHOT
cannot happen on them. Code that must not lose its write (``acquire_write_lock`` users) is only exercised faithfully on
an engine that registers the policy.
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.factory import register_sqlite_transaction_events
from app.database.models import Base, UserConfig

BUSY_TIMEOUT_MS = 5_000
# Generous so that a loaded machine does not fail the run before the unit reaches its first database call; a unit that
# never gets there still fails the run instead of passing without any contention.
UNIT_ARRIVAL_TIMEOUT_S = 10.0


def _begins(statement: str, keyword: str) -> bool:
    return statement.lstrip().upper().startswith(keyword)


@dataclass(frozen=True, slots=True)
class PolicyDb:
    factory: async_sessionmaker[AsyncSession]
    started: list[str]  # statements handed to the driver since the last ``hold_write_lock``
    finished: list[str]  # statements the driver completed since then

    def unit_waits_or_has_read(self) -> bool:
        """Whether a unit queued for the write lock (``BEGIN IMMEDIATE``) or its first read has returned.

        A lock request counts once issued, because the request itself blocks until the holder commits. A read counts
        only once it returned: the issue record is written before the driver runs the statement, and only a returned
        read guarantees that its session holds the snapshot the holder's commit makes stale. What this check leaves
        unwatched is described at ``run_while_another_writer_commits``.
        """
        return any(_begins(s, "BEGIN IMMEDIATE") for s in self.started) or any(_begins(s, "SELECT") for s in self.finished)


def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _record: object) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    cursor.close()


@asynccontextmanager
async def policy_database(path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PolicyDb]:
    """Create every table on a policy-running database that ``get_session()`` then hands out."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        connect_args={"check_same_thread": False},
        pool_size=4,
        max_overflow=2,
    )
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)
    register_sqlite_transaction_events(engine)
    started: list[str] = []
    finished: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _record_started(_conn: object, _cursor: object, statement: str, *_rest: object) -> None:
        started.append(statement)

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _record_finished(_conn: object, _cursor: object, statement: str, *_rest: object) -> None:
        finished.append(statement)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: factory)
    try:
        yield PolicyDb(factory, started, finished)
    finally:
        await engine.dispose()


async def hold_write_lock(db: PolicyDb) -> AsyncSession:
    """Open a writer that holds the database write lock, uncommitted, until the caller commits or closes it."""
    holder = db.factory()
    holder.add(
        UserConfig(
            id=str(uuid.uuid4()),
            config_key=f"lock-holder-{uuid.uuid4()}",
            config_value={},
            version="1.0.0",
            last_device_id="test",
            is_encrypted=False,
        )
    )
    await holder.flush()
    db.started.clear()
    db.finished.clear()
    return holder


async def wait_until(condition: Callable[[], bool], timeout_s: float) -> None:
    """Return once ``condition`` holds or the time is up; the caller decides what a timeout means."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while not condition() and loop.time() < deadline:
        await asyncio.sleep(0.005)


async def run_while_another_writer_commits(db: PolicyDb, start_unit: Callable[[], Coroutine[object, object, object]]) -> None:
    """Start the unit while another writer holds the write lock, let that writer commit, and wait for the unit.

    The writer commits only once the unit queued for the write lock or finished a read. Unprotected, the unit's write
    fails: on the lock the writer still holds, or after the commit on a read snapshot that predates it. Protected, the
    unit queued first and reads after the commit.

    Only the unit's first database interaction is guaranteed to contend with the writer. A unit that starts with a write
    queues behind the writer, the writer commits, and every session the unit opens afterwards starts past the commit, so
    a missing lock there goes unnoticed. A read in an earlier session lets the writer commit before the contended session
    has read.
    """
    holder = await hold_write_lock(db)
    unit = asyncio.create_task(start_unit())
    try:
        await wait_until(lambda: unit.done() or db.unit_waits_or_has_read(), UNIT_ARRIVAL_TIMEOUT_S)
        if unit.done():
            unit.result()  # a unit that failed before contending shows its own error, not a wait timeout
        assert db.unit_waits_or_has_read(), "the unit neither queued for the write lock nor finished a read"
        await holder.commit()
        await asyncio.wait_for(unit, timeout=BUSY_TIMEOUT_MS / 1000)
    finally:
        unit.cancel()
        await asyncio.gather(unit, return_exceptions=True)
        await holder.close()
