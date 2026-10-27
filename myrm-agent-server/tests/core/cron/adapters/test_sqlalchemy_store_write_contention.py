"""Post-run cron writes must not lose to a writer that commits between their read and their write.

The scheduler claims a due job by clearing ``next_run_at``; only the post-run ``save_job`` writes the next run time
back, and a monitor job's post-run ``save_monitor_state`` stores its new baseline. Under the deferred-read transaction
policy a read-then-write unit aborts with SQLITE_BUSY_SNAPSHOT when another connection commits in between,
``busy_timeout`` does not cover that, and the scheduler can only log the failure: a job whose ``save_job`` was lost stays
ACTIVE with no next run time and never fires again. The tests run the real transaction policy on a file database.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from myrm_agent_harness.infra.incremental.types import MonitorState
from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, RunStatus, Schedule, ScheduleKind

from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore
from tests.support.policy_sqlite import BUSY_TIMEOUT_MS, READ_GRACE_S, PolicyDb, hold_write_lock, policy_database, wait_until


@pytest_asyncio.fixture
async def policy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PolicyDb]:
    async with policy_database(tmp_path / "cron.db", monkeypatch) as db:
        yield db


def _job(job_id: str) -> CronJob:
    return CronJob(
        id=job_id,
        user_id="user",
        name=job_id,
        job_type=JobType.ROUTER,
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0),
        command="__probe__",
    )


async def _run_while_another_writer_commits(
    policy_db: PolicyDb, start_unit: Callable[[], Coroutine[object, object, object]]
) -> None:
    """Start the unit while another writer holds the write lock, let that writer commit, and wait for the unit."""
    holder = await hold_write_lock(policy_db)
    try:
        unit = asyncio.create_task(start_unit())
        # Unprotected, the unit reads within milliseconds and keeps that snapshot; protected, it waits for the lock
        # first and issues no read until the holder is done.
        await wait_until(policy_db.read_issued, READ_GRACE_S)
        await holder.commit()

        await asyncio.wait_for(unit, timeout=BUSY_TIMEOUT_MS / 1000)
    finally:
        await holder.close()


@pytest.mark.asyncio
async def test_save_job_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    store = SqlAlchemyCronStore()
    claimed = await store.save_job(_job("claimed"))
    finished = replace(
        claimed,
        next_run_at=datetime(2031, 1, 1, tzinfo=UTC),
        last_run_at=datetime(2030, 1, 1, tzinfo=UTC),
        last_status=RunStatus.OK,
        fire_count=1,
    )

    await _run_while_another_writer_commits(policy_db, lambda: store.save_job(finished))

    persisted = await store.get_job("claimed")
    assert persisted is not None
    assert persisted.next_run_at is not None
    assert persisted.last_status == RunStatus.OK
    assert persisted.fire_count == 1


@pytest.mark.asyncio
async def test_save_monitor_state_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    store = SqlAlchemyCronStore()
    await store.save_job(_job("watcher"))
    baseline = MonitorState(job_id="watcher", monitor_type="set", data={"seen": ["a"]})
    await store.save_monitor_state(baseline)

    updated = replace(baseline, data={"seen": ["a", "b"]})
    await _run_while_another_writer_commits(policy_db, lambda: store.save_monitor_state(updated))

    persisted = await store.get_monitor_state("watcher")
    assert persisted is not None
    assert persisted.data == {"seen": ["a", "b"]}
