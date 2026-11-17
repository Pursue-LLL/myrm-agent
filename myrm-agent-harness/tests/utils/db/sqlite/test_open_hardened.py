"""``open_hardened_async`` hands out a long-lived connection only once its setup has finished.

A caller that keeps the result must never hold a connection that lacks its hardening or its tables, so a step that
fails and a caller that is cancelled in the middle both close the connection before the error propagates.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from myrm_agent_harness.utils.db.sqlite import DEFAULT, SQLiteProfile, hardening, open_hardened_async

TIMEOUT_SECONDS = 10


async def pragma(connection: aiosqlite.Connection, name: str) -> object:
    async with connection.execute(f"PRAGMA {name}") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    return row[0]


async def assert_closed(connection: aiosqlite.Connection) -> None:
    """aiosqlite refuses every statement on a closed connection with a ``ValueError``."""
    with pytest.raises(ValueError):
        await connection.execute("SELECT 1")


class OpenedConnections:
    """Keeps the connection each step saw, since a failed open returns none."""

    def __init__(self) -> None:
        self.seen: list[aiosqlite.Connection] = []

    async def fail_hardening(self, connection: aiosqlite.Connection, *_args: object, **_kwargs: object) -> str:
        self.seen.append(connection)
        raise sqlite3.OperationalError("hardening failed")

    async def stall_hardening(self, connection: aiosqlite.Connection, *_args: object, **_kwargs: object) -> str:
        self.seen.append(connection)
        await asyncio.Event().wait()
        return "WAL"

    async def fail_prepare(self, connection: aiosqlite.Connection) -> None:
        self.seen.append(connection)
        raise ValueError("prepare failed")

    async def stall_prepare(self, connection: aiosqlite.Connection) -> None:
        self.seen.append(connection)
        await asyncio.Event().wait()


async def test_returns_a_connection_hardened_by_the_profile(tmp_path: Path) -> None:
    connection = await open_hardened_async(tmp_path / "db.sqlite", SQLiteProfile(page_size_bytes=8192))
    try:
        assert str(await pragma(connection, "journal_mode")).lower() == "wal"
        assert await pragma(connection, "foreign_keys") == 1
        assert await pragma(connection, "page_size") == 8192
    finally:
        await connection.close()


async def test_prepare_runs_on_the_hardened_connection_and_its_changes_stay(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    async def prepare(connection: aiosqlite.Connection) -> None:
        seen["foreign_keys"] = await pragma(connection, "foreign_keys")
        await connection.execute("CREATE TABLE facts (id TEXT PRIMARY KEY)")

    connection = await open_hardened_async(tmp_path / "db.sqlite", DEFAULT, prepare=prepare)
    try:
        assert seen["foreign_keys"] == 1
        await connection.execute("INSERT INTO facts (id) VALUES ('a')")
    finally:
        await connection.close()


async def test_a_failing_hardening_closes_the_connection_and_raises_its_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = OpenedConnections()
    monkeypatch.setattr(hardening, "harden_connection_async", opened.fail_hardening)

    with pytest.raises(sqlite3.OperationalError, match="hardening failed"):
        await open_hardened_async(tmp_path / "db.sqlite")

    await assert_closed(opened.seen[0])


async def test_a_failing_prepare_closes_the_connection_and_raises_its_error(tmp_path: Path) -> None:
    opened = OpenedConnections()

    with pytest.raises(ValueError, match="prepare failed"):
        await open_hardened_async(tmp_path / "db.sqlite", prepare=opened.fail_prepare)

    await assert_closed(opened.seen[0])


@pytest.mark.parametrize("stage", ["hardening", "prepare"])
async def test_a_cancelled_open_closes_the_connection(
    stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = OpenedConnections()
    prepare = None
    if stage == "hardening":
        monkeypatch.setattr(hardening, "harden_connection_async", opened.stall_hardening)
    else:
        prepare = opened.stall_prepare
    opening = asyncio.create_task(open_hardened_async(tmp_path / "db.sqlite", prepare=prepare))
    async with asyncio.timeout(TIMEOUT_SECONDS):
        while not opened.seen:
            await asyncio.sleep(0)

    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening

    await assert_closed(opened.seen[0])


async def test_a_close_that_fails_does_not_hide_the_error_that_ended_the_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = OpenedConnections()
    real_close = aiosqlite.Connection.close

    async def close_then_fail(connection: aiosqlite.Connection) -> None:
        await real_close(connection)
        raise RuntimeError("close failed")

    monkeypatch.setattr(aiosqlite.Connection, "close", close_then_fail)

    with pytest.raises(ValueError, match="prepare failed"):
        await open_hardened_async(tmp_path / "db.sqlite", prepare=opened.fail_prepare)

    await assert_closed(opened.seen[0])
