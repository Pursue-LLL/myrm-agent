"""A hardened connection that closes while a statement is unfinished must not keep the SQLite write lock.

``sqlite3_close_v2`` keeps a connection that still has an unfinished statement as a zombie, with its open transaction
and the WAL write lock, until that statement's cursor is garbage-collected. A task cancelled between a statement's
execute and the fetch of its ``RETURNING`` rows leaves exactly that, and the frames of the cancelled task keep the
cursor alive for as long as anything references the cancellation exception: every other writer waits out its busy
timeout meanwhile. The connections the factory hands out end their transaction before they close, so the lock goes
with them.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from myrm_agent_harness.utils.db.sqlite import RollbackBeforeCloseConnection, connect_async, open_hardened_async

TIMEOUT_SECONDS = 10

# Runs to completion at its first step, then keeps its rows pending: the statement stays unfinished until they are
# fetched or the cursor goes away.
CLAIM = "UPDATE claims SET owner = 'me' WHERE id = 1 RETURNING *"


def create_claims_table(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE claims (id INTEGER PRIMARY KEY, owner TEXT)")
        connection.execute("INSERT INTO claims (id) VALUES (1)")
        connection.commit()
    finally:
        connection.close()


def assert_write_lock_is_free(db_path: Path) -> None:
    """``timeout=0`` makes a held write lock fail at once instead of waiting it out."""
    other = sqlite3.connect(db_path, timeout=0)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.rollback()
    finally:
        other.close()


async def test_a_claim_cancelled_before_its_row_is_fetched_leaves_no_write_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "claims.db"
    create_claims_table(db_path)
    claimed = asyncio.Event()

    async def claim_and_wait() -> None:
        async with connect_async(db_path) as connection:
            cursor = await connection.execute(CLAIM)
            claimed.set()
            await asyncio.Event().wait()
            await cursor.fetchone()

    claimer = asyncio.create_task(claim_and_wait())
    async with asyncio.timeout(TIMEOUT_SECONDS):
        await claimed.wait()
    claimer.cancel()
    with pytest.raises(asyncio.CancelledError) as cancelled:
        await claimer

    # ``cancelled`` still references the abandoned claim's frames and so its cursor, as the frames of a cancelled task
    # do until the garbage collector runs: the lock must be gone while that cursor is alive.
    assert_write_lock_is_free(db_path)
    assert cancelled.value.__traceback__ is not None


async def test_a_long_lived_connection_closed_with_an_unfinished_claim_leaves_no_write_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "claims.db"
    create_claims_table(db_path)
    connection = await open_hardened_async(db_path)

    claim = await connection.execute(CLAIM)
    await connection.close()

    # ``claim`` is still referenced here, as an abandoned cursor is by the frames of a cancelled task.
    assert_write_lock_is_free(db_path)
    assert claim is not None


def test_closing_a_connection_twice_is_harmless(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "db.sqlite", factory=RollbackBeforeCloseConnection)

    connection.close()
    connection.close()
