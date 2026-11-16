"""What a dead or stopping scheduler leaves behind in the database is reported once, counted fairly, and never lost.

Each scenario runs real schedulers over one SQLite file, one after the other, the way successive server processes
share it. A process dies without a stop when its tasks are cancelled and nothing else runs, which is what an event
loop that closes does to the runs it leaves behind; its in-flight markers stay in the table, and the next scheduler's
start turns them into interrupted-run records. A graceful stop records its runs itself and counts nothing. The
scenarios are the ones that decide whether a job survives a crash, a crash loop and a string of deploys.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.cron.engine import scheduler as scheduler_module
from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronConfig,
    CronJob,
    JobResult,
    JobStatus,
    JobType,
    RunNowOutcome,
    RunStatus,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore
from tests.support.policy_sqlite import policy_database

HOURLY = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
HOURLY_CRON = Schedule(kind=ScheduleKind.CRON, expr="0 * * * *", stagger_ms=0)
CRASHED = "Interrupted: the server stopped before this run finished"
_PATIENCE_S = 20


class _Runner:
    """Finishes a run at once, fails it, or holds it until ``release``; ``attempts`` counts every run that began."""

    def __init__(self, *, hold: frozenset[str] = frozenset(), fail: frozenset[str] = frozenset()) -> None:
        self.hold = hold
        self.fail = fail
        self.attempts = 0
        self.unwind_s = 0.0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.attempts += 1
        self.entered.set()
        if job.name in self.hold:
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                await asyncio.sleep(self.unwind_s)
                raise
        failed = job.name in self.fail
        return JobResult(success=not failed, output="ok", error="boom" if failed else None)


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


@dataclass
class Process:
    """One scheduler process over the shared database."""

    store: SqlAlchemyCronStore
    scheduler: CronScheduler
    runner: _Runner

    @classmethod
    async def boot(cls, runner: _Runner, *, start: bool = True) -> Process:
        store = SqlAlchemyCronStore()
        scheduler = CronScheduler(store, {JobType.AGENT: runner}, _Delivery(), config=CronConfig(max_concurrent=4))
        if start:
            await scheduler.start()
        return cls(store, scheduler, runner)

    async def add(
        self,
        name: str,
        schedule: Schedule = HOURLY,
        *,
        due: bool = True,
        job_type: JobType = JobType.AGENT,
        command: str | None = None,
        active_hours: ActiveHours | None = None,
        cooldown_seconds: int = 0,
        last_run_at: datetime | None = None,
        fire_count: int = 0,
    ) -> CronJob:
        """An enabled job whose slot came due a second ago, or is booked an hour ahead."""
        job = CronJob(
            id=name,
            name=name,
            job_type=job_type,
            schedule=schedule,
            prompt="prompt",
            command=command,
            active_hours=active_hours,
            cooldown_seconds=cooldown_seconds,
            last_run_at=last_run_at,
            fire_count=fire_count,
            next_run_at=datetime.now(UTC) + (timedelta(seconds=-1) if due else timedelta(hours=1)),
        )
        return await self.store.save_job(job)

    async def stored(self, name: str) -> CronJob:
        found = await self.store.get_job(name)
        assert found is not None
        return found

    async def make_due(self, name: str) -> None:
        await self.store.save_job(replace(await self.stored(name), next_run_at=datetime.now(UTC) - timedelta(seconds=1)))

    async def tick(self) -> None:
        self.runner.entered.clear()
        await self.scheduler._on_tick()

    async def wait_in_flight(self) -> None:
        await asyncio.wait_for(self.runner.entered.wait(), timeout=_PATIENCE_S)

    async def drain(self) -> None:
        async with asyncio.timeout(_PATIENCE_S):
            while self.scheduler._bg_tasks:
                await asyncio.gather(*list(self.scheduler._bg_tasks), return_exceptions=True)

    async def die(self) -> None:
        """End without a stop: the tasks are cancelled and nothing is written, like an event loop that closes."""
        tasks = list(self.scheduler._bg_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def markers(self) -> list[str]:
        return [job_id for job_id, _ in await self.store.list_running()]

    async def errors(self, name: str, source: str) -> list[str | None]:
        """The error text of the job's run records written by ``source``."""
        return [run.error for run in await self.store.list_runs(name, limit=100) if run.trigger_source == source]


async def _life(name: str, *, new_slot: bool, expect_run: bool) -> int:
    """One process life that ends in its run: boot, let a new slot arrive if asked, wait for the run, then die."""
    runner = _Runner(hold=frozenset({name}))
    process = await Process.boot(runner)
    if new_slot:
        await process.make_due(name)
        await process.tick()
    if expect_run:
        await process.wait_in_flight()
    else:
        await asyncio.sleep(0.2)
    await process.die()
    return runner.attempts


@pytest_asyncio.fixture(autouse=True)
async def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    for name in ("_MIN_REFIRE_GAP_S", "_WATCHDOG_INTERVAL_S", "_STARTUP_TICK_DELAY_S"):
        monkeypatch.setattr(scheduler_module, name, 3600.0)
    async with policy_database(tmp_path / "cron.db", monkeypatch):
        yield


@pytest.mark.parametrize(
    ("schedule", "veteran"),
    [(HOURLY, False), (HOURLY, True), (HOURLY_CRON, True)],
    ids=["interval-fresh", "interval-veteran", "cron-veteran"],
)
async def test_a_killed_recurring_run_is_reported_once_and_the_job_keeps_its_next_slot(schedule: Schedule, veteran: bool) -> None:
    history = {"last_run_at": datetime.now(UTC) - timedelta(hours=2), "fire_count": 5} if veteran else {}
    first = await Process.boot(_Runner(hold=frozenset({"job"})))
    await first.add("job", schedule, **history)  # type: ignore[arg-type]
    await first.tick()
    await first.wait_in_flight()
    assert await first.markers() == ["job"]
    await first.die()

    second = await Process.boot(_Runner())
    await second.drain()

    stored = await second.stored("job")
    assert await second.errors("job", "recovery") == [CRASHED]
    assert (stored.status, stored.consecutive_failures, stored.last_status) == (JobStatus.ACTIVE, 1, RunStatus.ERROR)
    assert stored.next_run_at is not None and second.runner.attempts == 0
    assert await second.markers() == []
    await second.scheduler.stop()


async def test_a_killed_one_shot_is_delivered_again_within_its_grace() -> None:
    first = await Process.boot(_Runner(hold=frozenset({"reminder"})))
    await first.add("reminder", Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC)))
    await first.tick()
    await first.wait_in_flight()
    await first.die()

    second = await Process.boot(_Runner())
    await second.drain()

    assert second.runner.attempts == 1 and (await second.stored("reminder")).status == JobStatus.COMPLETED
    assert await second.errors("reminder", "recovery") == [CRASHED]
    assert await second.markers() == []
    await second.scheduler.stop()


async def test_runs_that_end_in_any_ordinary_way_leave_no_marker_and_no_interrupted_record() -> None:
    now = datetime.now(UTC)
    closed = ActiveHours(start=(now + timedelta(hours=2)).strftime("%H:%M"), end=(now + timedelta(hours=3)).strftime("%H:%M"))
    runner = _Runner(hold=frozenset({"deleted"}), fail=frozenset({"failing"}))
    process = await Process.boot(runner)
    for name in ("normal", "failing", "deleted"):
        await process.add(name)
    await process.add("windowed", active_hours=closed)
    await process.add("cooled", cooldown_seconds=3600, last_run_at=now - timedelta(seconds=10))
    await process.add("no-runner", job_type=JobType.ROUTER, command="__probe__")

    await process.tick()
    await process.wait_in_flight()
    await process.store.delete_job_cascade("deleted")  # removed while its run is in flight
    runner.release.set()
    await process.drain()

    async def interrupted_runs() -> list[str]:
        runs = await process.store.list_runs(limit=1000)
        return [run.job_id for run in runs if (run.error or "").startswith("Interrupted:")]

    assert await process.markers() == [] and await interrupted_runs() == []
    await process.scheduler.stop()
    restarted = await Process.boot(_Runner())
    await restarted.drain()
    assert await restarted.markers() == [] and await interrupted_runs() == []
    await restarted.scheduler.stop()


async def test_a_manual_run_inside_the_cooldown_leaves_no_marker_and_books_nothing() -> None:
    process = await Process.boot(_Runner())
    await process.add("cooled", due=False, cooldown_seconds=3600, last_run_at=datetime.now(UTC) - timedelta(seconds=10))
    before = await process.stored("cooled")

    assert await process.scheduler.run_now("cooled") == RunNowOutcome.STARTED
    await process.drain()

    after = await process.stored("cooled")
    assert process.runner.attempts == 1 and await process.markers() == []
    assert await process.errors("cooled", "manual") == [None]
    assert (after.next_run_at, after.fire_count, after.consecutive_failures) == (before.next_run_at, 0, 0)
    await process.scheduler.stop()
    restarted = await Process.boot(_Runner())
    await restarted.drain()
    assert await restarted.errors("cooled", "recovery") == [] and await restarted.markers() == []
    await restarted.scheduler.stop()


async def test_a_loop_that_ends_mid_run_keeps_the_marker_until_the_next_start_reports_it() -> None:
    first = await Process.boot(_Runner(hold=frozenset({"job"})))
    await first.add("job")
    await first.tick()
    await first.wait_in_flight()
    await first.die()

    assert await first.markers() == ["job"] and (await first.stored("job")).consecutive_failures == 0

    second = await Process.boot(_Runner())
    await second.drain()
    assert await second.markers() == [] and (await second.stored("job")).consecutive_failures == 1
    assert await second.errors("job", "recovery") == [CRASHED]
    await second.scheduler.stop()


async def test_a_one_shot_whose_every_run_kills_the_process_is_paused_after_three_attempts() -> None:
    seed = await Process.boot(_Runner(), start=False)
    await seed.add("crashy", Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC)))

    attempts = [await _life("crashy", new_slot=False, expect_run=life < 3) for life in range(4)]

    stored = await seed.stored("crashy")
    assert attempts == [1, 1, 1, 0]
    assert (stored.status, stored.consecutive_failures, stored.next_run_at) == (JobStatus.PAUSED, 3, None)
    assert len(await seed.errors("crashy", "recovery")) == 3 and await seed.markers() == []


async def test_a_recurring_job_whose_every_slot_kills_the_process_is_paused_after_three_attempts() -> None:
    seed = await Process.boot(_Runner(), start=False)
    await seed.add("poison", due=False)

    attempts = [await _life("poison", new_slot=life < 3, expect_run=life < 3) for life in range(4)]

    stored = await seed.stored("poison")
    assert attempts == [1, 1, 1, 0]
    assert (stored.status, stored.consecutive_failures, stored.next_run_at) == (JobStatus.PAUSED, 3, None)


async def test_a_recurring_job_killed_once_is_not_run_again_by_the_restarts_that_follow() -> None:
    seed = await Process.boot(_Runner(), start=False)
    await seed.add("poison")

    attempts = [await _life("poison", new_slot=False, expect_run=life == 0) for life in range(4)]

    stored = await seed.stored("poison")
    assert attempts == [1, 0, 0, 0]
    assert stored.status == JobStatus.ACTIVE and stored.next_run_at is not None
    assert len(await seed.errors("poison", "recovery")) == 1


async def test_three_graceful_stops_never_count_against_a_healthy_long_job() -> None:
    seed = await Process.boot(_Runner(), start=False)
    await seed.add("healthy", due=False)
    for _ in range(3):
        process = await Process.boot(_Runner(hold=frozenset({"healthy"})))
        await process.make_due("healthy")
        await process.tick()
        await process.wait_in_flight()
        await process.scheduler.stop()
        await process.drain()
    last = await Process.boot(_Runner())
    await last.drain()

    stored = await seed.stored("healthy")
    assert (stored.status, stored.consecutive_failures) == (JobStatus.ACTIVE, 0) and stored.next_run_at is not None
    assert len(await seed.errors("healthy", "shutdown")) == 3
    assert await seed.errors("healthy", "recovery") == [] and await seed.markers() == []
    await last.scheduler.stop()


async def test_a_stop_fits_the_desktop_budget_even_when_the_runs_unwind_slowly() -> None:
    runner = _Runner(hold=frozenset({f"slow-{n}" for n in range(4)}))
    runner.unwind_s = 30
    process = await Process.boot(runner)
    for n in range(4):
        await process.add(f"slow-{n}")
    await process.tick()
    async with asyncio.timeout(_PATIENCE_S):
        while runner.attempts < 4:
            await asyncio.sleep(0.01)
    assert len(await process.markers()) == 4

    started = time.monotonic()
    await process.scheduler.stop()
    elapsed = time.monotonic() - started

    assert elapsed < 1.5, "the desktop shell waits two seconds for a graceful exit"
    assert await process.markers() == [] and len(await process.store.list_runs(limit=100)) == 4
    await process.die()
