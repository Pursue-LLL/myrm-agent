"""A manual run is a trial: the task runs once, leaves a record, and nothing that decides its next run moves.

``run_now`` starts one run of an active task that is not already running. The run ignores the active window, a
cooldown and the stagger delay, books no slot and counts no fire; when it ends only the task's last-run fields change,
so a recurring task keeps its next slot and fire budget, a one-time reminder is neither completed nor deleted, and a
failed trial costs no failure. The one guard that still applies is the task's own end: an expired task, or one at its
fire limit, is paused as it would be by a scheduled run. These scenarios drive the real scheduler, executor, manager
and the ``cron_manage`` tool over the in-memory store; only the runner is a stand-in.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.cron import RunNowOutcome
from myrm_agent_harness.toolkits.cron.cron_agent_tools import create_cron_tools
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronJob,
    CronJobPatch,
    CronNotice,
    CronNoticeKind,
    JobResult,
    JobStatus,
    RunStatus,
    Schedule,
    ScheduleKind,
)
from tests.support.cron_manager_stack import ManagerStack, make_manager_stack

HOURLY = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
TOP_OF_THE_HOUR = Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *", tz="UTC")
MANUAL = "manual"
_STAGGER_WAIT_S = 300


class _Runner:
    """Plays the results queued in ``results`` (success when none is left); holds every run while ``gate`` is clear."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.gate.set()
        self.entered = asyncio.Event()
        self.results: list[JobResult] = []
        self.calls = 0

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.calls += 1
        self.entered.set()
        await self.gate.wait()
        return self.results.pop(0) if self.results else JobResult(success=True, output="done")


@dataclass
class Lab:
    stack: ManagerStack
    runner: _Runner
    notices: list[CronNotice] = field(default_factory=list)

    async def create(self, name: str = "job", schedule: Schedule = HOURLY, **options: object) -> CronJob:
        return await self.create_in_state(name, schedule, options)

    async def create_in_state(self, name: str, schedule: Schedule, state: dict[str, object]) -> CronJob:
        """Create the job through the manager, then put the stored job into ``state`` (active hours go in at creation)."""
        rest = dict(state)
        job = await self.stack.create(name, schedule, active_hours=rest.pop("active_hours", None))  # type: ignore[arg-type]
        if rest:
            await self.stack.rewrite(job.id, **rest)
        return await self.stack.stored(job.id)

    async def run_to_the_end(self, job: CronJob) -> RunNowOutcome:
        outcome = await self.stack.scheduler.run_now(job.id)
        await self.stack.settle()
        return outcome

    async def tool(self, **args: object) -> str:
        return str(await create_cron_tools(self.stack.manager, current_model="m", chat_id="c")[0].ainvoke(args))


@pytest.fixture
def lab() -> Lab:
    notices: list[CronNotice] = []

    async def collect(notice: CronNotice) -> None:
        notices.append(notice)

    runner = _Runner()
    return Lab(make_manager_stack(runner, collect), runner, notices)


class TestATrialLeavesTheScheduleAlone:
    async def test_a_recurring_task_keeps_its_slot_and_its_fire_budget(self, lab: Lab) -> None:
        job = await lab.create(max_fires=3)

        assert await lab.run_to_the_end(job) == RunNowOutcome.STARTED

        stored = await lab.stack.stored(job.id)
        assert stored.next_run_at == job.next_run_at and stored.fire_count == 0
        assert stored.status == JobStatus.ACTIVE and stored.consecutive_failures == 0
        assert stored.last_status == RunStatus.OK and stored.last_run_at is not None
        (record,) = await lab.stack.records(job.id)
        assert record.trigger_source == MANUAL and record.status == RunStatus.OK

    async def test_a_one_time_reminder_is_neither_completed_nor_deleted(self, lab: Lab) -> None:
        reminder = await lab.create(
            schedule=Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + timedelta(days=1))
        )
        assert reminder.delete_after_run

        await lab.run_to_the_end(reminder)

        stored = await lab.stack.stored(reminder.id)
        assert stored.status == JobStatus.ACTIVE and stored.next_run_at == reminder.next_run_at
        assert stored.last_status == RunStatus.OK

    @pytest.mark.parametrize(
        "schedule", [HOURLY, Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + timedelta(days=1))]
    )
    async def test_a_failed_trial_costs_the_task_no_failure(self, lab: Lab, schedule: Schedule) -> None:
        job = await lab.create(schedule=schedule)
        lab.runner.results.append(JobResult(success=False, error="boom", retry_safe=False))

        await lab.run_to_the_end(job)

        stored = await lab.stack.stored(job.id)
        assert stored.status == JobStatus.ACTIVE and stored.consecutive_failures == 0
        assert stored.next_run_at == job.next_run_at
        assert stored.last_status == RunStatus.ERROR and stored.last_error == "boom"
        assert [r.status for r in await lab.stack.records(job.id)] == [RunStatus.ERROR]

    async def test_a_trial_the_loop_guard_cut_off_is_announced_as_a_failed_run_because_nothing_pauses_the_task(
        self, lab: Lab
    ) -> None:
        job = await lab.create()
        lab.runner.results.append(
            JobResult(success=False, error="RUNAWAY_CIRCUIT_BREAKER: pump repeated 5 times", circuit_broken=True)
        )

        await lab.run_to_the_end(job)

        stored = await lab.stack.stored(job.id)
        assert (stored.status, stored.paused_reason) == (JobStatus.ACTIVE, None)
        assert [notice.kind for notice in lab.notices] == [CronNoticeKind.RUN_FAILED]

    @pytest.mark.parametrize(
        "result",
        [
            JobResult(success=True, skipped=True, skip_reason="nothing new"),
            JobResult(success=False, skip_reason="rate limited", retry_at=datetime.now(UTC) + timedelta(hours=5)),
        ],
        ids=["skipped", "deferred"],
    )
    async def test_a_skipped_or_deferred_trial_leaves_only_its_record(self, lab: Lab, result: JobResult) -> None:
        job = await lab.create()
        before = replace(job)
        lab.runner.results.append(result)

        await lab.run_to_the_end(job)

        assert await lab.stack.stored(job.id) == before
        (record,) = await lab.stack.records(job.id)
        assert record.status == RunStatus.SKIPPED and record.trigger_source == MANUAL

    async def test_the_output_it_delivered_is_the_baseline_of_the_next_duplicate_check(self, lab: Lab) -> None:
        job = await lab.create(deduplicate=True)

        await lab.run_to_the_end(job)

        assert (await lab.stack.stored(job.id)).last_output_hash


class TestATrialIsNotHeldBack:
    async def test_it_runs_outside_the_active_window_and_inside_a_cooldown(self, lab: Lab) -> None:
        now = datetime.now(UTC)
        outside = ActiveHours(
            start=(now + timedelta(hours=2)).strftime("%H:%M"), end=(now + timedelta(hours=3)).strftime("%H:%M")
        )
        windowed = await lab.create("windowed", active_hours=outside)
        cooling = await lab.create("cooling", cooldown_seconds=3600, last_run_at=now - timedelta(minutes=5))

        for job in (windowed, cooling):
            assert await lab.run_to_the_end(job) == RunNowOutcome.STARTED
            assert (await lab.stack.stored(job.id)).next_run_at == job.next_run_at

        assert lab.runner.calls == 2

    async def test_it_does_not_wait_for_the_stagger_delay(self, lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
        job = await lab.create(schedule=TOP_OF_THE_HOUR)
        # A stagger would sleep for the whole window and ``run_to_the_end`` would time out instead of finishing.
        monkeypatch.setattr(random, "randint", lambda low, high: high)

        await lab.run_to_the_end(job)

        assert lab.runner.calls == 1

    @pytest.mark.parametrize(
        ("changes", "notice"),
        [
            ({"expires_at": datetime.now(UTC) - timedelta(minutes=1)}, CronNoticeKind.JOB_EXPIRED),
            ({"max_fires": 2, "fire_count": 2}, CronNoticeKind.JOB_MAX_FIRES_REACHED),
        ],
        ids=["expired", "fire_limit"],
    )
    async def test_the_end_of_the_task_still_pauses_it_with_a_notice(
        self, lab: Lab, changes: dict[str, object], notice: CronNoticeKind
    ) -> None:
        job = await lab.create_in_state("job", HOURLY, changes)

        await lab.run_to_the_end(job)

        stored = await lab.stack.stored(job.id)
        assert stored.status == JobStatus.PAUSED and stored.next_run_at is None
        assert lab.runner.calls == 0 and await lab.stack.records(job.id) == []
        assert [n.kind for n in lab.notices] == [notice]


class TestOneRunAtATime:
    async def test_a_second_request_while_the_task_runs_is_refused_and_starts_nothing(self, lab: Lab) -> None:
        job = await lab.create()
        lab.runner.gate.clear()

        first = await lab.stack.scheduler.run_now(job.id)
        second = await lab.stack.scheduler.run_now(job.id)
        await lab.runner.entered.wait()
        lab.runner.gate.set()
        await lab.stack.settle()

        assert (first, second) == (RunNowOutcome.STARTED, RunNowOutcome.ALREADY_RUNNING)
        assert lab.runner.calls == 1 and len(await lab.stack.records(job.id)) == 1
        assert await lab.run_to_the_end(job) == RunNowOutcome.STARTED and lab.runner.calls == 2

    async def test_a_run_that_a_slot_started_also_blocks_it(self, lab: Lab) -> None:
        job = await lab.create()
        lab.runner.gate.clear()
        lab.stack.scheduler._launch(job)

        assert await lab.stack.scheduler.run_now(job.id) == RunNowOutcome.ALREADY_RUNNING

        lab.runner.gate.set()
        await lab.stack.settle()
        assert lab.runner.calls == 1

    async def test_a_slot_that_is_being_booked_blocks_it_too(self, lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
        job = await lab.create(next_run_at=datetime.now(UTC) - timedelta(seconds=1))
        booking, release = asyncio.Event(), asyncio.Event()
        book = lab.stack.store.advance_next_run

        async def held_booking(job_id: str, *, next_run_at: datetime) -> bool:
            booking.set()
            await release.wait()
            return await book(job_id, next_run_at=next_run_at)

        monkeypatch.setattr(lab.stack.store, "advance_next_run", held_booking)
        admission = asyncio.create_task(lab.stack.scheduler._admit(job))
        await booking.wait()

        during_the_booking = await lab.stack.scheduler.run_now(job.id)
        release.set()
        await admission
        await lab.stack.settle()

        assert during_the_booking == RunNowOutcome.ALREADY_RUNNING
        assert [record.trigger_source for record in await lab.stack.records(job.id)] == ["cron"]
        assert not lab.stack.scheduler._admitting

    async def test_a_booking_that_fails_leaves_the_task_free_to_run(
        self, lab: Lab, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = await lab.create(next_run_at=datetime.now(UTC) - timedelta(seconds=1))

        async def failing_booking(job_id: str, *, next_run_at: datetime) -> bool:
            raise OSError("store unavailable")

        monkeypatch.setattr(lab.stack.store, "advance_next_run", failing_booking)
        await lab.stack.scheduler._admit(job)

        assert lab.runner.calls == 0 and not lab.stack.scheduler._admitting
        assert await lab.run_to_the_end(job) == RunNowOutcome.STARTED

    async def test_a_task_that_is_missing_or_not_active_is_not_run(self, lab: Lab) -> None:
        paused = await lab.create("paused", status=JobStatus.PAUSED)
        done = await lab.create("done", status=JobStatus.COMPLETED)

        outcomes = [await lab.stack.scheduler.run_now(job_id) for job_id in ("nope", paused.id, done.id)]

        assert outcomes == [RunNowOutcome.NOT_FOUND, RunNowOutcome.NOT_ACTIVE, RunNowOutcome.NOT_ACTIVE]
        assert lab.runner.calls == 0


class TestWhileTheTrialRuns:
    async def test_a_task_deleted_meanwhile_stays_deleted(self, lab: Lab) -> None:
        job = await lab.create()
        lab.runner.gate.clear()
        await lab.stack.scheduler.run_now(job.id)
        await lab.runner.entered.wait()

        assert await lab.stack.manager.delete_job(job.id)
        lab.runner.gate.set()
        await lab.stack.settle()

        assert await lab.stack.store.get_job(job.id) is None

    async def test_an_edit_made_meanwhile_is_kept(self, lab: Lab) -> None:
        job = await lab.create()
        lab.runner.gate.clear()
        await lab.stack.scheduler.run_now(job.id)
        await lab.runner.entered.wait()

        await lab.stack.manager.update_job(job.id, CronJobPatch(name="renamed"))
        lab.runner.gate.set()
        await lab.stack.settle()

        stored = await lab.stack.stored(job.id)
        assert stored.name == "renamed" and stored.last_status == RunStatus.OK


class TestTheRunAction:
    async def test_it_tells_the_model_what_the_request_came_to(self, lab: Lab) -> None:
        job = await lab.create()
        lab.runner.gate.clear()

        started = await lab.tool(action="run", job_id=job.id)
        again = await lab.tool(action="run", job_id=job.id)
        lab.runner.gate.set()
        await lab.stack.settle()
        unknown = await lab.tool(action="run", job_id="nope")
        await lab.stack.manager.pause_job(job.id)
        paused = await lab.tool(action="run", job_id=job.id)

        assert started == f"Task {job.id} triggered."
        assert again == f"Task {job.id} is already running."
        assert unknown == "Task nope not found or not active."
        assert paused == f"Task {job.id} not found or not active."
