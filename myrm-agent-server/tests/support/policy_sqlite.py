"""A file SQLite database that runs the production transaction policy, for tests of read-then-write units.

[INPUT]
- app.database.factory::register_sqlite_transaction_events (POS: the deferred-read / immediate-write policy)
- app.database.models::Base (POS: ORM metadata of every table)

[OUTPUT]
- policy_database: build the schema on a policy-running database that ``get_session()`` then hands out
- hold_write_lock: a writer that keeps the write lock, uncommitted, until the caller lets go
- PolicyDb.read_issued / wait_until: observe whether a unit has started reading

[POS]
The plain ``sqlite+aiosqlite`` engines most fixtures use do not run the policy, so a write lost to SQLITE_BUSY_SNAPSHOT
cannot happen on them. Code that must not lose its write (``acquire_write_lock`` users) is only exercised faithfully on
an engine that registers the policy.
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.factory import register_sqlite_transaction_events
from app.database.models import Base, UserConfig

BUSY_TIMEOUT_MS = 5_000
READ_GRACE_S = 0.5


@dataclass(frozen=True, slots=True)
class PolicyDb:
    factory: async_sessionmaker[AsyncSession]
    statements: list[str]

    def read_issued(self) -> bool:
        """Whether any session ran a SELECT since the last ``hold_write_lock``."""
        return any(statement.lstrip().upper().startswith("SELECT") for statement in self.statements)


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
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _record(_conn: object, _cursor: object, statement: str, *_rest: object) -> None:
        statements.append(statement)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: factory)
    try:
        yield PolicyDb(factory, statements)
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
    db.statements.clear()
    return holder


async def wait_until(condition: Callable[[], bool], timeout_s: float) -> None:
    """Return once ``condition`` holds or the time is up; the caller decides what a timeout means."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while not condition() and loop.time() < deadline:
        await asyncio.sleep(0.005)
