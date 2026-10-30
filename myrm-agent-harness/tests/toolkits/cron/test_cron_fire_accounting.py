"""``max_fires`` limits how often a job executes: a run that skips or is deferred never spends one.

The scheduler counts a fire when a run starts, before the pre-flight condition and the runner have had their say,
so the closing write of a skipped or deferred run hands it back. Every test drives the real scheduler, executor and
manager over the in-memory store; only the runner and the pre-flight condition are stand-ins.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

USER = "user-1"
EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)

_SUCCEEDED = JobResult(success=True, output="done")
_FAILED = JobResult(success=False, error="boom")
_SKIPPED = JobResult(success=True, skipped=True, skip_reason="budget_blocked")
_DEFERRED = JobResult(
    success=False, error="limit", skip_reason="usage_limit", retry_at=datetime.now(UTC) + timedelta(hours=3)
)


class _Delivery:
    def __init__(self) -> None:
        self.delivered: list[str] = []

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        self.delivered.append(result.output)


class _Runner:
    def __init__(self) -> None:
        self.result = _SUCCEEDED
        self.runs = 0

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.runs += 1
        return self.result


class _Condition:
    """The pre-flight condition: the job's own check that decides whether this slot is worth a run."""

    def __init__(self) -> None:
        self.met = False

    async def evaluate(self, job: CronJob) -> tuple[bool, str]:
        return self.met, ""


@dataclass
class Stack:
    store: InMemoryCronStore
    manager: CronManager
    scheduler: CronScheduler
    runner: _Runner
    condition: _Condition
    delivery: _Delivery

    async def create(self, **options: object) -> CronJob:
        return await self.manager.create_job(USER, "job", JobType.AGENT, EVERY_HOUR, prompt="prompt", **options)

    async def dispatch(self, job: CronJob, result: JobResult | None = None) -> None:
        """What the timer does for a due job: read it, claim it, hand the snapshot to the scheduler."""
        if result is not None:
            self.runner.result = result
        snapshot = await self.store.get_job(job.id)
        await self.store.claim_due([job.id])
        await self.scheduler._execute_and_persist(snapshot)

    async def stored(self, job: CronJob) -> CronJob:
        found = await self.store.get_job(job.id)
        assert found is not None
        return found


@pytest.fixture
def stack() -> Stack:
    store = InMemoryCronStore()
    runner, condition, delivery = _Runner(), _Condition(), _Delivery()
    scheduler = CronScheduler(
        store, {JobType.AGENT: runner}, delivery, config=CronConfig(max_per_user=1), pre_condition=condition
    )
    return Stack(store, CronManager(store, scheduler), scheduler, runner, condition, delivery)


@pytest.mark.parametrize("result", [_SKIPPED, _DEFERRED], ids=["skipped", "deferred"])
async def test_a_skipped_or_deferred_run_leaves_the_only_fire_for_a_real_run(stack: Stack, result: JobResult) -> None:
    job = await stack.create(max_fires=1)

    await stack.dispatch(job, result)

    stored = await stack.stored(job)
    assert stored.fire_count == 0 and stored.status == JobStatus.ACTIVE and stored.last_status == RunStatus.SKIPPED

    await stack.dispatch(job, _SUCCEEDED)
    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stack.runner.runs == 2 and stack.delivery.delivered == ["done"]
    assert stored.fire_count == 1 and stored.status == JobStatus.PAUSED


async def test_a_pre_flight_condition_that_is_not_met_never_uses_up_the_limit(stack: Stack) -> None:
    job = await stack.create(max_fires=2, pre_condition_script="check")

    for _ in range(5):
        await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stack.runner.runs == 0
    assert stored.fire_count == 0 and stored.status == JobStatus.ACTIVE and stored.last_status == RunStatus.SKIPPED

    stack.condition.met = True
    for _ in range(3):
        await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stack.runner.runs == 2 and stored.fire_count == 2 and stored.status == JobStatus.PAUSED


async def test_the_limit_counts_executions_however_many_skips_come_between(stack: Stack) -> None:
    job = await stack.create(max_fires=2)

    for result in (_SKIPPED, _SUCCEEDED, _DEFERRED, _SKIPPED, _SUCCEEDED, _SUCCEEDED):
        await stack.dispatch(job, result)

    stored = await stack.stored(job)
    assert stack.delivery.delivered == ["done", "done"]
    assert stored.fire_count == 2 and stored.status == JobStatus.PAUSED


async def test_a_failed_run_still_spends_its_fire(stack: Stack) -> None:
    job = await stack.create(max_fires=1)

    await stack.dispatch(job, _FAILED)

    stored = await stack.stored(job)
    assert stored.fire_count == 1 and stored.last_status == RunStatus.ERROR

    await stack.dispatch(job)

    assert stack.runner.runs == 1 and (await stack.stored(job)).status == JobStatus.PAUSED


async def test_a_skip_never_takes_the_count_below_zero(stack: Stack) -> None:
    job = await stack.create(max_fires=1)
    stack.runner.result = _SKIPPED

    # Straight to the executor: the scheduler did not count a fire for this run.
    await stack.scheduler._executor.run_and_record(job, stack.runner)

    assert (await stack.stored(job)).fire_count == 0
