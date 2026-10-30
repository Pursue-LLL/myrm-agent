"""A pre-flight condition that cannot reach a verdict fails the run; one that says no still skips it.

A script that crashed or timed out has not said the job may stay silent, so the run is a failed one: it is recorded,
delivered and counted, and it can alert and auto-pause. Nothing ran, so the next regular slot is the retry. Every
test drives the real scheduler, executor and manager over the in-memory store; only the runner, the delivery and the
pre-flight condition are stand-ins.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.protocols import PreFlightConditionError
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    FailureAlertConfig,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

USER = "user-1"
EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
CRASH = "exit code 1: RuntimeError: all_sources_failed"
ALERT_AFTER_TWO = FailureAlertConfig(after=2, cooldown_seconds=900)


class _Delivery:
    def __init__(self) -> None:
        self.results: list[JobResult] = []

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        self.results.append(result)

    @property
    def alerts(self) -> list[str]:
        return [r.output for r in self.results if r.success and r.output.startswith("Cron job")]


class _Runner:
    def __init__(self) -> None:
        self.runs = 0

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.runs += 1
        return JobResult(success=True, output="done")


class _Condition:
    """The job's own check: crashes, says no, or lets the run go ahead, after taking ``delay`` seconds."""

    def __init__(self) -> None:
        self.crash: str | None = CRASH
        self.says_no = False
        self.delay = 0.0

    async def evaluate(self, job: CronJob) -> tuple[bool, str]:
        await asyncio.sleep(self.delay)
        if self.crash is not None:
            raise PreFlightConditionError(self.crash)
        return not self.says_no, ""


@dataclass
class Stack:
    store: InMemoryCronStore
    manager: CronManager
    scheduler: CronScheduler
    runner: _Runner
    condition: _Condition
    delivery: _Delivery

    async def create(self, schedule: Schedule = EVERY_HOUR, **options: object) -> CronJob:
        return await self.manager.create_job(
            USER, "job", JobType.AGENT, schedule, prompt="prompt", pre_condition_script="check", **options
        )

    async def dispatch(self, job: CronJob) -> None:
        """What the timer does for a due job: read it, claim it, hand the snapshot to the scheduler."""
        snapshot = await self.store.get_job(job.id)
        await self.store.claim_due([job.id])
        await self.scheduler._execute_and_persist(snapshot)
        await asyncio.sleep(0)  # the failure alert is sent from a task the executor starts

    async def stored(self, job: CronJob) -> CronJob:
        found = await self.store.get_job(job.id)
        assert found is not None
        return found

    async def last_run(self, job: CronJob):
        (run,) = await self.store.list_runs(job.id, limit=1)
        return run


@pytest.fixture
def stack() -> Stack:
    store = InMemoryCronStore()
    runner, condition, delivery = _Runner(), _Condition(), _Delivery()
    scheduler = CronScheduler(
        store, {JobType.AGENT: runner}, delivery, config=CronConfig(max_per_user=1), pre_condition=condition
    )
    return Stack(store, CronManager(store, scheduler), scheduler, runner, condition, delivery)


async def test_a_probe_that_cannot_decide_is_a_failed_run_that_does_no_work(stack: Stack) -> None:
    job = await stack.create()

    await stack.dispatch(job)

    run, stored = await stack.last_run(job), await stack.stored(job)
    assert run.status == RunStatus.ERROR and run.error == f"Pre-flight probe failed: {CRASH}"
    assert stack.runner.runs == 0
    assert stored.last_status == RunStatus.ERROR and stored.last_error == run.error
    assert stored.consecutive_failures == 1 and stored.fire_count == 1 and stored.status == JobStatus.ACTIVE
    assert [r.error for r in stack.delivery.results] == [run.error]


async def test_the_next_attempt_is_the_next_regular_slot_not_a_backoff_retry(stack: Stack) -> None:
    job = await stack.create()

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.next_run_at is not None and stored.last_run_at is not None
    assert stored.next_run_at - stored.last_run_at > timedelta(minutes=30)


async def test_the_first_failure_alerts_without_waiting_for_the_configured_count(stack: Stack) -> None:
    job = await stack.create(failure_alert=ALERT_AFTER_TWO)

    await stack.dispatch(job)

    (alert,) = stack.delivery.alerts
    assert "failed 1 consecutive times" in alert and f"Last error: Pre-flight probe failed: {CRASH}" in alert


async def test_three_failed_slots_in_a_row_pause_the_job(stack: Stack) -> None:
    job = await stack.create()

    for _ in range(3):
        await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.status == JobStatus.PAUSED and stored.next_run_at is None and stored.consecutive_failures == 3
    assert stack.runner.runs == 0


async def test_a_one_shot_job_is_paused_with_its_error_instead_of_being_consumed(stack: Stack) -> None:
    job = await stack.create(Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + timedelta(hours=1)))
    assert job.delete_after_run

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.status == JobStatus.PAUSED and stored.last_error == f"Pre-flight probe failed: {CRASH}"
    assert stack.runner.runs == 0


async def test_a_probe_that_recovers_runs_the_job_and_clears_the_failures(stack: Stack) -> None:
    job = await stack.create()
    await stack.dispatch(job)

    stack.condition.crash = None
    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stack.runner.runs == 1 and stored.consecutive_failures == 0 and stored.status == JobStatus.ACTIVE
    assert stored.last_status == RunStatus.OK


async def test_a_probe_that_says_no_is_still_a_skip(stack: Stack) -> None:
    job = await stack.create(failure_alert=ALERT_AFTER_TWO)
    stack.condition.crash, stack.condition.says_no = None, True

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.last_status == RunStatus.SKIPPED and stored.consecutive_failures == 0 and stored.fire_count == 0
    assert stack.runner.runs == 0 and stack.delivery.results == []


async def test_a_failed_probe_run_covers_the_probe_but_a_normal_run_does_not(stack: Stack) -> None:
    job = await stack.create()
    stack.condition.delay = 0.05
    await stack.dispatch(job)
    assert (await stack.last_run(job)).duration_ms >= 45

    stack.condition.crash, stack.condition.delay = None, 0.4
    await stack.dispatch(job)
    assert (await stack.last_run(job)).duration_ms < 200
