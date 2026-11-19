"""A due recurring job is booked before its run starts; nothing that happens to the run can leave it without a next slot.

The scheduler books a job's next slot with one conditional write and only then launches the run, and it registers the
run as in flight before the run's task exists. These scenarios drive the real scheduler, executor and manager over the
in-memory store: a run that is still going, a closing write that fails, a missing runner, a slot that arrives while its
predecessor still runs, a job that is paused, edited or admitted twice, a one-time job, and jobs that cannot be booked
or rescheduled. Only the runner and the delivery are stand-ins; a slot comes due by rewriting the stored
``next_run_at``, and the test ticks the scheduler itself.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.engine import scheduler as scheduler_module
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronJobPatch,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
_NO_TIMER_S = 3600.0
_WAIT_S = 5


class _GatedRunner:
    """A runner whose runs stay in flight until ``release`` is set; it counts calls and the peak overlap."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.calls: list[str] = []
        self.in_flight = 0
        self.peak = 0

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.calls.append(job.id)
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await self.release.wait()
        finally:
            self.in_flight -= 1
        return JobResult(success=True, output="done")


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


class _FaultyStore(InMemoryCronStore):
    """Refuses to write the jobs in ``fail_saves`` and to book the jobs in ``fail_bookings``."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_saves: set[str] = set()
        self.fail_bookings: set[str] = set()

    async def save_job(self, job: CronJob) -> CronJob:
        if job.id in self.fail_saves:
            raise RuntimeError("disk is full")
        return await super().save_job(job)

    async def advance_next_run(self, job_id: str, *, next_run_at: datetime) -> bool:
        if job_id in self.fail_bookings:
            raise RuntimeError("store is unavailable")
        return await super().advance_next_run(job_id, next_run_at=next_run_at)


@dataclass
class Stack:
    store: InMemoryCronStore
    manager: CronManager
    scheduler: CronScheduler
    runner: _GatedRunner

    async def create(self, name: str = "job", schedule: Schedule = EVERY_HOUR) -> CronJob:
        return await self.manager.create_job(name, JobType.AGENT, schedule, prompt="prompt")

    async def make_due(self, job: CronJob, *, ago: timedelta = timedelta(seconds=1)) -> None:
        stored = await self.stored(job)
        stored.next_run_at = datetime.now(UTC) - ago
        await self.store.save_job(stored)

    async def stored(self, job: CronJob) -> CronJob:
        found = await self.store.get_job(job.id)
        assert found is not None
        return found

    async def wait_for_runs(self, count: int) -> None:
        async with asyncio.timeout(_WAIT_S):
            while len(self.runner.calls) < count:
                await asyncio.sleep(0)

    async def settle(self) -> None:
        """Wait until no run is in flight."""
        async with asyncio.timeout(_WAIT_S):
            while self.scheduler._in_flight:
                await asyncio.sleep(0)

    async def let_anything_late_start(self) -> None:
        """A run that should not start would have done so within a few loop passes."""
        for _ in range(20):
            await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def _no_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scheduler's timers must never fire between the test's own ticks."""
    for name in ("_MIN_REFIRE_GAP_S", "_WATCHDOG_INTERVAL_S", "_STARTUP_TICK_DELAY_S"):
        monkeypatch.setattr(scheduler_module, name, _NO_TIMER_S)


@asynccontextmanager
async def _running(store: InMemoryCronStore) -> AsyncIterator[Stack]:
    runner = _GatedRunner()
    scheduler = CronScheduler(store, {JobType.AGENT: runner}, _Delivery(), config=CronConfig(max_concurrent=4))
    stack = Stack(store, CronManager(store, scheduler), scheduler, runner)
    await scheduler.start()
    try:
        yield stack
    finally:
        runner.release.set()
        await scheduler.stop()


@pytest_asyncio.fixture
async def stack() -> AsyncIterator[Stack]:
    async with _running(InMemoryCronStore()) as stack:
        yield stack


async def test_the_next_slot_is_booked_while_the_run_is_still_going(stack: Stack) -> None:
    job = await stack.create()
    await stack.make_due(job)

    await stack.scheduler._on_tick()
    await stack.wait_for_runs(1)

    running = await stack.stored(job)
    assert running.status == JobStatus.ACTIVE and stack.scheduler._in_flight[job.id] == 1
    assert running.next_run_at is not None and running.next_run_at > datetime.now(UTC)

    stack.runner.release.set()
    await stack.settle()
    closed = await stack.stored(job)
    assert closed.last_status == RunStatus.OK
    assert closed.next_run_at is not None and closed.next_run_at > datetime.now(UTC)


async def test_a_closing_write_that_fails_leaves_the_booked_next_slot() -> None:
    store = _FaultyStore()
    async with _running(store) as stack:
        stack.runner.release.set()
        job = await stack.create()
        await stack.make_due(job)
        store.fail_saves.add(job.id)

        await stack.scheduler._on_tick()
        await stack.settle()
        store.fail_saves.clear()

        stored = await stack.stored(job)
        assert stack.runner.calls == [job.id] and stored.status == JobStatus.ACTIVE
        assert stored.next_run_at is not None and stored.next_run_at > datetime.now(UTC)


async def test_a_job_whose_type_has_no_runner_keeps_a_next_slot(stack: Stack) -> None:
    shell = CronJob(
        id="shell-1",
        name="shell",
        job_type=JobType.SHELL,
        schedule=EVERY_HOUR,
        command="echo hi",
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    await stack.store.save_job(shell)

    await stack.scheduler._on_tick()
    await stack.settle()

    stored = await stack.stored(shell)
    assert stack.runner.calls == []
    assert stored.next_run_at is not None and stored.next_run_at > datetime.now(UTC)


async def test_a_slot_past_its_misfire_grace_is_skipped_and_the_next_slot_booked(stack: Stack) -> None:
    job = await stack.create()
    await stack.make_due(job, ago=timedelta(hours=2))

    await stack.scheduler._on_tick()
    await stack.settle()

    stored = await stack.stored(job)
    assert stack.runner.calls == [] and stored.last_status == RunStatus.SKIPPED
    assert stored.next_run_at is not None and stored.next_run_at > datetime.now(UTC)


async def test_ticks_while_the_job_runs_start_no_second_run(stack: Stack) -> None:
    job = await stack.create()
    await stack.make_due(job)
    await stack.scheduler._on_tick()
    await stack.wait_for_runs(1)

    await stack.make_due(job, ago=timedelta(seconds=12))  # the next slot arrives while the run is still going
    for _ in range(5):
        await stack.scheduler._on_tick()
    await stack.let_anything_late_start()

    assert stack.runner.calls == [job.id] and stack.runner.peak == 1
    assert stack.scheduler._in_flight[job.id] == 1

    stack.runner.release.set()
    await stack.settle()
    closed = await stack.stored(job)
    assert closed.next_run_at is not None and closed.next_run_at > datetime.now(UTC)


async def test_a_job_paused_before_its_admission_is_not_run(stack: Stack) -> None:
    job = await stack.create()
    await stack.make_due(job)
    due_snapshot = await stack.stored(job)
    await stack.manager.pause_job(job.id)

    await stack.scheduler._admit(due_snapshot)
    await stack.let_anything_late_start()

    assert stack.runner.calls == []


async def test_a_job_edited_before_its_admission_is_not_run_for_the_old_slot(stack: Stack) -> None:
    job = await stack.create()
    await stack.make_due(job)
    due_snapshot = await stack.stored(job)
    slower = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=7_200_000, stagger_ms=0)
    await stack.manager.update_job(job.id, CronJobPatch(schedule=slower))

    await stack.scheduler._admit(due_snapshot)
    await stack.let_anything_late_start()

    assert stack.runner.calls == []


async def test_two_admissions_of_one_slot_launch_one_run(stack: Stack) -> None:
    job = await stack.create()
    await stack.make_due(job)
    due_snapshot = await stack.stored(job)

    await asyncio.gather(stack.scheduler._admit(due_snapshot), stack.scheduler._admit(due_snapshot))
    await stack.wait_for_runs(1)
    await stack.let_anything_late_start()

    assert stack.runner.calls == [job.id]


async def test_a_one_time_job_stays_due_until_it_completes(stack: Stack) -> None:
    job = await stack.create(schedule=Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + timedelta(hours=1)))
    await stack.make_due(job)
    due = (await stack.stored(job)).next_run_at

    await stack.scheduler._on_tick()
    await stack.wait_for_runs(1)

    running = await stack.stored(job)
    assert running.status == JobStatus.ACTIVE and running.next_run_at == due

    stack.runner.release.set()
    await stack.settle()
    assert await stack.store.get_job(job.id) is None


async def test_jobs_that_cannot_be_booked_or_rescheduled_do_not_hold_back_the_others(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = _FaultyStore()
    async with _running(store) as stack:
        stack.runner.release.set()
        unbookable = await stack.create("unbookable")
        unschedulable = await stack.create("unschedulable")
        healthy = await stack.create("healthy")
        await stack.make_due(unbookable)
        await stack.make_due(unschedulable, ago=timedelta(hours=2))
        await stack.make_due(healthy)
        store.fail_bookings.add(unbookable.id)
        store.fail_saves.add(unschedulable.id)

        with caplog.at_level(logging.WARNING):
            await stack.scheduler._on_tick()
            await stack.settle()

        assert stack.runner.calls == [healthy.id] and stack.scheduler._tick_errors == 0
        assert f"Job {unbookable.id} not dispatched: could not book its next run" in caplog.text
        assert f"Cron tick: job {unschedulable.id} could not be handled" in caplog.text


async def test_a_launched_run_is_in_flight_from_the_launch_until_it_closes(stack: Stack) -> None:
    job = await stack.create()

    stack.scheduler._launch(await stack.stored(job))
    assert stack.scheduler._in_flight[job.id] == 1  # registered before the run's task has had a single pass

    stack.runner.release.set()
    await stack.settle()
    assert job.id not in stack.scheduler._in_flight
