"""The policy-database helper really makes a unit that reads before it locks lose its write, and fails loudly when it cannot.

[INPUT]
- tests.support.policy_sqlite::policy_database / hold_write_lock / run_while_another_writer_commits / PolicyDb (POS: file SQLite
  running the production transaction policy with a record of the statements it ran, a writer that keeps the write lock, and
  a run that lets another writer commit in front of a unit)
- app.database.factory::acquire_write_lock (POS: SQLite write lock for a transaction that reads before it writes)
- app.database.models::UserConfig (POS: the table the units read and write)

[OUTPUT]
- a read-then-write unit without the write lock loses its write to the competing commit
- a unit that takes the lock before its first read waits for the writer, reads its commit and writes
- a unit that fails before it contends shows its own error; a unit that never touches the database fails the run
- a unit that does not start with a write-lock request followed by a read fails the run, whatever lock it takes later
- what counts as arrived: a lock request once issued, a read once it returned; statements from before the writer took
  the lock never count

[POS]
The write-contention tests of every ``acquire_write_lock`` user only prove something if the helper really builds the interleaving
a missing lock loses to. These cases pin that, so a helper that released the competing writer too early cannot let a removed
lock pass unnoticed.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database.factory import acquire_write_lock
from app.database.models import UserConfig
from tests.support.policy_sqlite import PolicyDb, hold_write_lock, policy_database, run_while_another_writer_commits


def _config_row(key: str) -> UserConfig:
    return UserConfig(
        id=str(uuid.uuid4()), config_key=key, config_value={}, version="1.0.0", last_device_id="test", is_encrypted=False
    )


async def _read_then_write(db: PolicyDb, *, locked: bool = False) -> None:
    """A unit that reads, then writes something derived from what it read; ``locked`` takes the write lock first."""
    async with db.factory() as session:
        if locked:
            await acquire_write_lock(session)
        rows = (await session.execute(select(func.count()).select_from(UserConfig))).scalar_one()
        session.add(_config_row(f"unit-{rows}"))
        await session.commit()


async def test_a_unit_that_reads_before_locking_loses_its_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with policy_database(tmp_path / "policy.db", monkeypatch) as db:
        with pytest.raises(OperationalError, match="database is locked"):
            await run_while_another_writer_commits(db, lambda: _read_then_write(db))


async def test_a_unit_that_locks_before_reading_waits_for_the_writer_and_reads_its_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with policy_database(tmp_path / "policy.db", monkeypatch) as db:
        await run_while_another_writer_commits(db, lambda: _read_then_write(db, locked=True))

        async with db.factory() as session:
            keys = set((await session.execute(select(UserConfig.config_key))).scalars())
        assert "unit-1" in keys  # the unit counted the one row the writer committed, so it read after that commit


async def test_a_unit_that_fails_before_contending_shows_its_own_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fails_first() -> None:
        raise ValueError("unit bug")

    async with policy_database(tmp_path / "policy.db", monkeypatch) as db:
        with pytest.raises(ValueError, match="unit bug"):
            await run_while_another_writer_commits(db, fails_first)


async def test_a_unit_that_never_touches_the_database_fails_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def touches_nothing() -> None:
        return None

    async with policy_database(tmp_path / "policy.db", monkeypatch) as db:
        with pytest.raises(AssertionError, match="neither queued"):
            await run_while_another_writer_commits(db, touches_nothing)


async def test_a_unit_whose_first_transaction_is_a_write_fails_the_run_though_a_later_session_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with policy_database(tmp_path / "policy.db", monkeypatch) as db:

        async def writes_then_locks_and_reads() -> None:
            async with db.factory() as session:  # queues behind the writer, which then commits: the next session starts past it
                session.add(_config_row("earlier-write"))
                await session.commit()
            await _read_then_write(db, locked=True)

        with pytest.raises(AssertionError, match="did not start with a write-lock request"):
            await run_while_another_writer_commits(db, writes_then_locks_and_reads)


async def test_a_unit_whose_first_transaction_only_reads_fails_the_run_though_a_later_session_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with policy_database(tmp_path / "policy.db", monkeypatch) as db:

        async def reads_then_locks_and_reads() -> None:
            async with db.factory() as session:  # a read that returned is all the run waits for before the writer commits
                await session.execute(select(func.count()).select_from(UserConfig))
            await _read_then_write(db, locked=True)

        with pytest.raises(AssertionError, match="did not start with a write-lock request"):
            await run_while_another_writer_commits(db, reads_then_locks_and_reads)


def test_a_read_counts_as_arrived_once_it_returned_and_a_lock_request_once_it_was_issued() -> None:
    reading = PolicyDb(async_sessionmaker(), started=["SELECT 1"], finished=[])
    assert not reading.unit_waits_or_has_read()  # issued but not returned: the snapshot is not yet guaranteed

    read = PolicyDb(async_sessionmaker(), started=["SELECT 1"], finished=["SELECT 1"])
    assert read.unit_waits_or_has_read()

    queued = PolicyDb(async_sessionmaker(), started=["BEGIN IMMEDIATE"], finished=[])
    assert queued.unit_waits_or_has_read()  # the request blocks until the holder commits, so issued is enough


async def test_statements_from_before_the_writer_took_the_lock_never_count_as_arrival(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with policy_database(tmp_path / "policy.db", monkeypatch) as db:
        async with db.factory() as session:  # a test's own seeding read, finished before the writer takes the lock
            await session.execute(select(func.count()).select_from(UserConfig))
        assert db.unit_waits_or_has_read()  # left in the record, that read would pass for the unit's arrival

        holder = await hold_write_lock(db)
        try:
            assert not db.unit_waits_or_has_read()
        finally:
            await holder.close()
