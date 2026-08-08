"""Tests for the deferred-read / immediate-write SQLite transaction policy.

Guards the fix for the "database is locked" storm on read-only endpoints:
every transaction used to run ``BEGIN IMMEDIATE``, which made concurrent
snapshot reads contend for the SQLite write lock. Under WAL, reads must stay
lock-free (deferred BEGIN), and only genuine writers escalate to IMMEDIATE.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database.factory import register_sqlite_transaction_events

_BUSY_TIMEOUT_MS = 300


def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _record: object) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    cursor.close()


@pytest.fixture()
async def engine(tmp_path: Path) -> AsyncEngine:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'txn.db'}",
        future=True,
        connect_args={"check_same_thread": False},
        pool_size=3,
        max_overflow=1,
    )
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)
    register_sqlite_transaction_events(engine)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_read_not_blocked_by_concurrent_write_lock(engine: AsyncEngine, tmp_path: Path) -> None:
    """A WAL snapshot read must succeed while another connection holds the write lock.

    Regression guard: with the old blanket ``BEGIN IMMEDIATE`` this read would
    contend for the write lock and fail with ``database is locked``.
    """
    lock = sqlite3.connect(str(tmp_path / "txn.db"))
    try:
        lock.execute("BEGIN IMMEDIATE")
        lock.execute("INSERT INTO t (v) VALUES ('held')")
        async with engine.connect() as conn:
            row = (await conn.execute(text("SELECT count(*) FROM t"))).scalar_one()
        assert row == 0  # uncommitted write is invisible to the snapshot
    finally:
        lock.rollback()
        lock.close()


@pytest.mark.asyncio
async def test_write_contends_for_write_lock(engine: AsyncEngine, tmp_path: Path) -> None:
    """A genuine writer must escalate to BEGIN IMMEDIATE and respect busy_timeout.

    With the write lock held elsewhere and a short busy_timeout, the insert must
    surface ``database is locked`` rather than silently proceed — proving writes
    still serialize on the write lock.
    """
    lock = sqlite3.connect(str(tmp_path / "txn.db"))
    lock.execute("BEGIN IMMEDIATE")
    lock.execute("INSERT INTO t (v) VALUES ('held')")
    try:
        with pytest.raises(OperationalError):
            async with engine.begin() as conn:
                await conn.execute(text("INSERT INTO t (v) VALUES ('new')"))
    finally:
        lock.rollback()
        lock.close()


@pytest.mark.asyncio
async def test_read_then_write_transaction_commits(engine: AsyncEngine, tmp_path: Path) -> None:
    """Read-then-write flows (deferred snapshot kept) still commit correctly.

    A transaction that reads first must not lose its ability to write: the
    deferred snapshot is kept for consistency, and the write commits normally
    when no concurrent writer holds the lock.
    """
    async with engine.begin() as conn:
        base = (await conn.execute(text("SELECT count(*) FROM t"))).scalar_one()
        await conn.execute(text("INSERT INTO t (v) VALUES (:v)"), {"v": f"n{base}"})
    async with engine.connect() as conn:
        total = (await conn.execute(text("SELECT count(*) FROM t"))).scalar_one()
    assert total == base + 1
