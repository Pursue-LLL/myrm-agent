"""A dispatch guard that refuses a due slot says so in a run record and books the next slot; it never stalls the job.

The guards (expiry, fire limit, cooldown, active hours, ``skip_if_active``, a missing runner) run on a job whose next
slot is already booked. A refused scheduled slot is a SKIPPED run that never began: it is recorded, the next slot is
booked, and the cooldown anchor stays where it was. A run that a trigger started leaves no record. Every test drives
the real scheduler and executor over the in-memory store; only the runner and the notice callback are stand-ins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.cron import CronConfig, CronScheduler
from myrm_agent_harness.toolkits.cron.engine.helpers import is_within_active_hours
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronJob,
    CronNotice,
    CronNoticeKind,
    CronRunRecord,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

HOURLY = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
_DUE_SINCE = timedelta(seconds=1)


class _Runner:
    def __init__(self) -> None:
        self.runs = 0

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.runs += 1
        return JobResult(success=True, output="done")


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


def _job(**overrides: object) -> CronJob:
    fields: dict[str, object] = {
        "id": "job-1",
        "name": "Water the plants",
        "job_type": JobType.AGENT,
        "schedule": HOURLY,
        "prompt": "prompt",
        "next_run_at": datetime.now(UTC) - _DUE_SINCE,
    }
    return CronJob(**{**fields, **overrides})  # type: ignore[arg-type]


def _window_excluding_now() -> ActiveHours:
    now = datetime.now(UTC)
    return ActiveHours(
        start=(now + timedelta(hours=2)).strftime("%H:%M"), end=(now + timedelta(hours=3)).strftime("%H:%M")
    )


@dataclass
class Stack:
    store: InMemoryCronStore
    scheduler: CronScheduler
    runner: _Runner
    notices: list[CronNotice] = field(default_factory=list)

    async def dispatch(self, job: CronJob, **options: str) -> CronJob:
        """Store the job and hand its snapshot to the scheduler, as the timer does once the job's next slot is booked."""
        await self.store.save_job(job)
        return await self.again(job, **options)

    async def again(self, job: CronJob, **options: str) -> CronJob:
        """Hand the stored job to the scheduler once more."""
        snapshot = await self.store.get_job(job.id)
        assert snapshot is not None
        await self.scheduler._dispatch(snapshot, **options)
        return await self.stored(job)

    async def stored(self, job: CronJob) -> CronJob:
        found = await self.store.get_job(job.id)
        assert found is not None
        return found

    async def records(self, job: CronJob) -> list[CronRunRecord]:
        return await self.store.list_runs(job.id)


@pytest.fixture
def stack() -> Stack:
    notices: list[CronNotice] = []

    async def record(notice: CronNotice) -> None:
        notices.append(notice)

    store, runner = InMemoryCronStore(), _Runner()
    scheduler = CronScheduler(store, {JobType.AGENT: runner}, _Delivery(), config=CronConfig(), on_notice=record)
    return Stack(store, scheduler, runner, notices)


async def test_an_expired_job_is_paused_with_no_next_run_and_no_run(stack: Stack) -> None:
    stored = await stack.dispatch(_job(expires_at=datetime.now(UTC) - timedelta(minutes=1)))

    assert stored.status == JobStatus.PAUSED and stored.next_run_at is None
    assert stack.runner.runs == 0 and await stack.records(stored) == []
    assert [notice.kind for notice in stack.notices] == [CronNoticeKind.JOB_EXPIRED]


async def test_a_job_at_its_fire_limit_is_paused_the_same_way(stack: Stack) -> None:
    stored = await stack.dispatch(_job(max_fires=2, fire_count=2))

    assert stored.status == JobStatus.PAUSED and stored.next_run_at is None
    assert stack.runner.runs == 0 and await stack.records(stored) == []
    assert [notice.kind for notice in stack.notices] == [CronNoticeKind.JOB_MAX_FIRES_REACHED]


async def test_a_cooldown_skip_is_recorded_and_the_next_slot_booked(stack: Stack) -> None:
    stored = await stack.dispatch(_job(cooldown_seconds=3600, last_run_at=datetime.now(UTC) - timedelta(minutes=10)))

    (record,) = await stack.records(stored)
    assert record.status == RunStatus.SKIPPED and record.output == "cooldown_active"
    assert stack.runner.runs == 0 and stored.fire_count == 0 and stored.last_status == RunStatus.SKIPPED
    assert stored.next_run_at is not None and stored.next_run_at > datetime.now(UTC)
    assert stack.notices == []


async def test_repeated_cooldown_skips_leave_the_cooldown_anchor_alone(stack: Stack) -> None:
    ran_at = datetime.now(UTC) - timedelta(minutes=10)
    job = _job(cooldown_seconds=3600, last_run_at=ran_at)
    await stack.store.save_job(job)

    for _ in range(3):
        stored = await stack.again(job)

    assert stored.last_run_at == ran_at and len(await stack.records(job)) == 3 and stack.runner.runs == 0
    await stack.store.save_job(replace(stored, last_run_at=datetime.now(UTC) - timedelta(hours=2)))
    await stack.again(job)
    assert stack.runner.runs == 1


async def test_a_slot_outside_the_active_hours_is_recorded_and_booked_inside_the_window(stack: Stack) -> None:
    window = _window_excluding_now()

    stored = await stack.dispatch(_job(active_hours=window))

    (record,) = await stack.records(stored)
    assert record.status == RunStatus.SKIPPED and record.output == "outside_active_hours"
    assert stack.runner.runs == 0 and stored.last_status == RunStatus.SKIPPED
    assert stored.next_run_at is not None and is_within_active_hours(window, now=stored.next_run_at)


async def test_a_guard_that_refuses_a_triggered_run_leaves_no_record(stack: Stack) -> None:
    due = datetime.now(UTC) - _DUE_SINCE
    job = _job(cooldown_seconds=3600, last_run_at=datetime.now(UTC) - timedelta(minutes=10), next_run_at=due)

    stored = await stack.dispatch(job, trigger_source="event")

    assert await stack.records(stored) == [] and stack.runner.runs == 0
    assert stored.next_run_at == due and stored.last_status is None


async def test_a_one_time_job_is_held_back_by_neither_cooldown_nor_active_hours(stack: Stack) -> None:
    once = Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) - _DUE_SINCE)

    stored = await stack.dispatch(
        _job(
            schedule=once,
            cooldown_seconds=3600,
            last_run_at=datetime.now(UTC) - timedelta(minutes=10),
            active_hours=_window_excluding_now(),
        )
    )

    assert stack.runner.runs == 1 and stored.status == JobStatus.COMPLETED


async def test_skip_if_active_refuses_a_second_instance_without_a_record(stack: Stack) -> None:
    job = _job(skip_if_active=True)
    stack.scheduler._in_flight[job.id] = 2  # this run and the one still running

    stored = await stack.dispatch(job)

    assert stack.runner.runs == 0 and await stack.records(stored) == []
    assert stored.next_run_at == job.next_run_at


async def test_a_job_whose_type_has_no_runner_runs_nothing(stack: Stack) -> None:
    stored = await stack.dispatch(_job(job_type=JobType.SHELL, command="echo hi"))

    assert stack.runner.runs == 0 and await stack.records(stored) == []


async def test_the_stagger_delay_is_waited_out_before_the_run(stack: Stack) -> None:
    staggered = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=100)

    with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
        await stack.dispatch(_job(schedule=staggered))

    sleep.assert_awaited_once()
    assert stack.runner.runs == 1


async def test_an_unexpected_error_is_contained_in_the_dispatch(stack: Stack, caplog: pytest.LogCaptureFixture) -> None:
    target = "myrm_agent_harness.toolkits.cron.engine.scheduler_dispatch.pre_execution_check"

    with patch(target, side_effect=RuntimeError("unexpected")), caplog.at_level(logging.WARNING):
        await stack.dispatch(_job())

    assert "Unhandled error in job job-1: unexpected" in caplog.text and stack.runner.runs == 0
