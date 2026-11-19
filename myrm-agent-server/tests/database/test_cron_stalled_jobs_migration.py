"""Upgrading re-arms enabled recurring cron jobs that have no next run time and pauses such one-time jobs.

An enabled job without a next run time is never run: nothing books it. The two migration statements book each recurring
one as due long ago, so the startup recovery books its real next slot without starting a run nobody asked for, and
pause each one-time one. Every other job is left as it is.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.cron.engine import scheduler as scheduler_module
from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
from myrm_agent_harness.toolkits.cron.serialization import schedule_to_dict
from myrm_agent_harness.toolkits.cron.types import CronConfig, CronJob, JobResult, JobType, RunStatus, Schedule, ScheduleKind
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore
from app.database import migrations
from app.database.migrations import MIGRATION_STATEMENTS, PAUSE_STALLED_ONCE_CRON_JOBS_SQL, REARM_STALLED_CRON_JOBS_SQL
from app.database.models import Base, CronJobModel

_FIRST = MIGRATION_STATEMENTS.index(REARM_STALLED_CRON_JOBS_SQL)
_EPOCH = datetime(1970, 1, 1)
_LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)
_NO_TIMER_S = 3600.0
_DRAIN_S = 30
_SCHEDULES = {
    "interval": Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
    "cron": Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *", stagger_ms=0),
    "once": Schedule(kind=ScheduleKind.ONCE, run_at=_LONG_AGO),
}
_STALLED_RECURRING = {"stalled-interval", "stalled-cron-with-history", "stalled-cron-new"}

type Snapshot = dict[str, tuple[str, datetime | None, datetime]]


@dataclass(frozen=True, slots=True)
class _Db:
    engine: AsyncEngine
    factory: async_sessionmaker[AsyncSession]

    async def snapshot(self) -> Snapshot:
        async with self.factory() as session:
            rows = (await session.execute(select(CronJobModel))).scalars().all()
            return {row.id: (row.status, row.next_run_at, row.updated_at) for row in rows}


class _Runner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.calls.append(job.id)
        return JobResult(success=True, output="ok")


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


def _job(
    job_id: str,
    schedule: str,
    *,
    status: str = "active",
    next_run_at: datetime | None = None,
    last_run_at: datetime | None = None,
) -> CronJobModel:
    return CronJobModel(
        id=job_id,
        name=job_id,
        job_type="agent",
        status=status,
        schedule=schedule_to_dict(_SCHEDULES[schedule]),
        prompt="x",
        model="m",
        next_run_at=next_run_at,
        last_run_at=last_run_at,
        created_at=_LONG_AGO,
        updated_at=_LONG_AGO,
    )


@pytest_asyncio.fixture
async def stalled_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Db]:
    """A database one statement before the two, holding stalled jobs next to jobs the migration must not touch."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", MIGRATION_STATEMENTS[:_FIRST])
    await migrations.run_migrations(engine)
    async with factory() as session:
        session.add_all(
            [
                _job("stalled-interval", "interval"),
                _job("stalled-cron-with-history", "cron", last_run_at=_LONG_AGO),
                _job("stalled-cron-new", "cron"),
                _job("stalled-once", "once"),
                _job("paused-recurring", "interval", status="paused"),
                _job("completed-once", "once", status="completed"),
                _job("healthy", "cron", next_run_at=datetime.now(UTC) + timedelta(days=1)),
            ]
        )
        await session.commit()
    monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", MIGRATION_STATEMENTS[: _FIRST + 2])
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: factory)
    yield _Db(engine, factory)
    await engine.dispose()


def test_both_statements_are_registered_in_order() -> None:
    assert MIGRATION_STATEMENTS[_FIRST : _FIRST + 2] == [REARM_STALLED_CRON_JOBS_SQL, PAUSE_STALLED_ONCE_CRON_JOBS_SQL]


async def test_stalled_recurring_jobs_are_rearmed_and_stalled_once_jobs_paused(stalled_db: _Db) -> None:
    before = await stalled_db.snapshot()
    upgraded_at = datetime.now(UTC).replace(tzinfo=None, microsecond=0)

    await migrations.run_migrations(stalled_db.engine)

    after = await stalled_db.snapshot()
    for job_id in _STALLED_RECURRING:
        status, next_run_at, updated_at = after[job_id]
        assert (status, next_run_at) == ("active", _EPOCH)
        assert updated_at >= upgraded_at
    assert after["stalled-once"][:2] == ("paused", None)
    untouched = before.keys() - _STALLED_RECURRING - {"stalled-once"}
    assert {job_id: after[job_id] for job_id in untouched} == {job_id: before[job_id] for job_id in untouched}


async def test_running_the_statements_again_changes_nothing(stalled_db: _Db) -> None:
    await migrations.run_migrations(stalled_db.engine)
    upgraded = await stalled_db.snapshot()

    async with stalled_db.engine.begin() as conn:
        changed = [
            (await conn.execute(text(sql))).rowcount for sql in (REARM_STALLED_CRON_JOBS_SQL, PAUSE_STALLED_ONCE_CRON_JOBS_SQL)
        ]

    assert changed == [0, 0]
    assert await stalled_db.snapshot() == upgraded


async def test_the_restart_books_the_real_next_slot_and_starts_no_run(stalled_db: _Db, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("_MIN_REFIRE_GAP_S", "_WATCHDOG_INTERVAL_S", "_STARTUP_TICK_DELAY_S"):
        monkeypatch.setattr(scheduler_module, name, _NO_TIMER_S)
    await migrations.run_migrations(stalled_db.engine)
    store, runner = SqlAlchemyCronStore(), _Runner()
    scheduler = CronScheduler(
        store=store, runners={JobType.AGENT: runner}, delivery=_Delivery(), config=CronConfig(max_concurrent=4)
    )

    await scheduler.start()
    await scheduler.stop()
    me = asyncio.current_task()
    async with asyncio.timeout(_DRAIN_S):
        await asyncio.gather(*(task for task in asyncio.all_tasks() if task is not me), return_exceptions=True)

    now = datetime.now(UTC)
    assert runner.calls == []
    for job_id in _STALLED_RECURRING:
        job = await store.get_job(job_id)
        assert job is not None
        assert job.next_run_at is not None and job.next_run_at.replace(tzinfo=UTC) > now
        assert job.last_status == RunStatus.SKIPPED
