"""``save_job`` must not lose its write to a writer that commits between its read and its write.

The scheduler claims a due job by clearing ``next_run_at``; only the post-run ``save_job`` writes the next run time
back. Under the deferred-read transaction policy a read-then-write unit aborts with SQLITE_BUSY_SNAPSHOT when another
connection commits in between, ``busy_timeout`` does not cover that, and the scheduler can only log the failure: the job
stays ACTIVE with no next run time and never fires again. The test runs the real transaction policy on a file database.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
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

    holder = await hold_write_lock(policy_db)
    try:
        save = asyncio.create_task(store.save_job(finished))
        # Unprotected, save_job reads the row within milliseconds and keeps that snapshot; protected, it waits for the
        # lock first and issues no read until the holder is done.
        await wait_until(policy_db.read_issued, READ_GRACE_S)
        await holder.commit()

        await asyncio.wait_for(save, timeout=BUSY_TIMEOUT_MS / 1000)
    finally:
        await holder.close()

    persisted = await store.get_job("claimed")
    assert persisted is not None
    assert persisted.next_run_at is not None
    assert persisted.last_status == RunStatus.OK
    assert persisted.fire_count == 1
