"""A pooled connection that SQLAlchemy discards mid-statement must not keep the SQLite write lock.

A task cancelled between a statement's execute and the fetch of its ``RETURNING`` rows leaves a write transaction open
on a cursor whose statement is unfinished. SQLAlchemy cannot tell where the driver stopped, so it discards the
connection by closing it. ``sqlite3_close_v2`` keeps a connection with an unfinished statement as a zombie that holds
its transaction, and the WAL write lock with it, until that cursor is garbage-collected, which the frames of the
cancelled task can postpone indefinitely: every other writer then waits out its busy timeout. The engine's connections
end their transaction before they close, so the lock goes with them.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import aiosqlite
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config.settings import settings
from app.database.factory import create_engine


@pytest.fixture()
async def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncEngine:
    monkeypatch.setattr(settings.database, "sqlite_path", str(tmp_path / "data.db"))
    engine = create_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_write_cancelled_before_its_returning_rows_are_fetched_leaves_no_write_lock(
    engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch_started = asyncio.Event()

    async def fetch_that_waits_to_be_cancelled(_cursor: aiosqlite.Cursor) -> list[sqlite3.Row]:
        fetch_started.set()
        await asyncio.Event().wait()
        return []

    # Installed once the pool holds its connection: opening one fetches the PRAGMA rows through the same method.
    monkeypatch.setattr(aiosqlite.Cursor, "fetchall", fetch_that_waits_to_be_cancelled)

    async def insert_returning() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO t (v) VALUES ('x') RETURNING id"))

    writer = asyncio.create_task(insert_returning())
    await fetch_started.wait()
    writer.cancel()
    with pytest.raises(asyncio.CancelledError) as cancelled:
        await writer

    # ``cancelled`` still references the abandoned statement's frames and so its cursor, as the frames of a cancelled
    # task do until the garbage collector runs: the lock must be gone while that cursor is alive.
    other = sqlite3.connect(tmp_path / "data.db", timeout=0)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.rollback()
    finally:
        other.close()
    assert cancelled.value.__traceback__ is not None
