"""A job is dispatched as a snapshot; the store, not the snapshot, decides what a run may do and what it leaves behind.

The user pauses, edits and deletes jobs while a dispatched run waits for its stagger delay or a concurrency slot,
while the runner works and while the result is delivered. Every test drives the real scheduler, executor and
manager over the in-memory store; only the runner, which performs the user's action in the middle of the run, is
a stand-in.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.engine.job_freshness import RUN_OWNED_FIELDS, adopt_latest
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronJobPatch,
    DeliveryConfig,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

USER = "user-1"
HOUR_MS = 3_600_000
EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=HOUR_MS, stagger_ms=0)
STAGGERED = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=HOUR_MS, stagger_ms=1000)
Action = Callable[[CronJob], Awaitable[object]]

_SUCCEEDED = JobResult(success=True, output="done")
_FAILED = JobResult(success=False, error="boom")
_SKIPPED = JobResult(success=True, skipped=True, skip_reason="nothing to do")
_DEFERRED = JobResult(success=True, retry_at=datetime.now(UTC) + timedelta(minutes=5), skip_reason="busy")
# Every way a run can end, with the status the job reports afterwards.
RUN_ENDINGS = [
    pytest.param(_SUCCEEDED, RunStatus.OK, id="succeeded"),
    pytest.param(_FAILED, RunStatus.ERROR, id="failed-within-retries"),
    pytest.param(_SKIPPED, RunStatus.SKIPPED, id="skipped"),
    pytest.param(_DEFERRED, RunStatus.SKIPPED, id="deferred"),
]


class _Delivery:
    def __init__(self) -> None:
        self.delivered: list[str] = []

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        self.delivered.append(result.output)


class _Runner:
    """Performs the user's action in the middle of the run, then reports ``result``."""

    def __init__(self) -> None:
        self.seen_prompts: list[str | None] = []
        self.during: Action | None = None
        self.result = JobResult(success=True, output="done")

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.seen_prompts.append(job.prompt)
        if self.during is not None:
            await self.during(job)
        return self.result


@dataclass
class Stack:
    store: InMemoryCronStore
    manager: CronManager
    scheduler: CronScheduler
    runner: _Runner
    delivery: _Delivery

    async def create(self, *, schedule: Schedule = EVERY_HOUR, **options: object) -> CronJob:
        return await self.manager.create_job(USER, "job", JobType.AGENT, schedule, prompt="old prompt", **options)

    async def dispatch(self, job: CronJob) -> None:
        """What the timer does: read the due job, claim it, hand the snapshot to the scheduler."""
        snapshot = await self.store.get_job(job.id)
        await self.store.claim_due([job.id])
        await self.scheduler._execute_and_persist(snapshot)

    async def stored(self, job: CronJob) -> CronJob:
        found = await self.store.get_job(job.id)
        assert found is not None
        return found

    async def pause(self, job: CronJob) -> object:
        return await self.manager.pause_job(job.id, USER)

    async def delete(self, job: CronJob) -> object:
        return await self.manager.delete_job(job.id, USER)

    async def edit(self, job: CronJob, **fields_to_change: object) -> object:
        return await self.manager.update_job(job.id, USER, CronJobPatch(**fields_to_change))


@pytest.fixture
def stack() -> Stack:
    store = InMemoryCronStore()
    runner, delivery = _Runner(), _Delivery()
    scheduler = CronScheduler(store, {JobType.AGENT: runner}, delivery, config=CronConfig(max_per_user=1))
    return Stack(store, CronManager(store, scheduler), scheduler, runner, delivery)


def _act_during_the_stagger_wait(monkeypatch: pytest.MonkeyPatch, action: Callable[[], Awaitable[object]]) -> None:
    """The scheduler's stagger delay is its only ``asyncio.sleep``; the user's action lands inside it."""
    pending = [action]

    async def sleep(_: float) -> None:
        if pending:
            await pending.pop()()

    monkeypatch.setattr(asyncio, "sleep", sleep)


async def _leave_alone() -> None:
    return None


async def _wait_until_parked_on_the_slot(stack: Stack, job: CronJob) -> None:
    async with asyncio.timeout(5):
        while job.id not in stack.scheduler._active_jobs:
            await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# The user acts while the run is in flight
# ---------------------------------------------------------------------------


async def test_an_untouched_job_runs_once_and_is_rescheduled(stack: Stack) -> None:
    job = await stack.create()

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert len(stack.runner.seen_prompts) == 1
    assert stored.status == JobStatus.ACTIVE and stored.fire_count == 1 and stored.last_status == RunStatus.OK
    assert stored.next_run_at is not None


@pytest.mark.parametrize(("result", "last_status"), RUN_ENDINGS)
async def test_a_pause_during_the_run_survives_every_way_a_run_can_end(
    stack: Stack, result: JobResult, last_status: RunStatus
) -> None:
    job = await stack.create()
    stack.runner.result = result
    stack.runner.during = stack.pause

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.status == JobStatus.PAUSED and stored.last_status == last_status


@pytest.mark.parametrize(
    "result", [_SUCCEEDED, _FAILED, _SKIPPED, _DEFERRED], ids=["succeeded", "failed", "skipped", "deferred"]
)
async def test_a_deleted_job_is_not_brought_back_by_any_way_a_run_can_end(stack: Stack, result: JobResult) -> None:
    job = await stack.create()
    stack.runner.result = result
    stack.runner.during = stack.delete

    await stack.dispatch(job)

    assert await stack.store.get_job(job.id) is None


@pytest.mark.parametrize("result", [_SKIPPED, _DEFERRED], ids=["skipped", "deferred"])
async def test_a_skipped_or_deferred_run_of_a_deleted_job_records_nothing(stack: Stack, result: JobResult) -> None:
    job = await stack.create()
    stack.runner.result = result
    stack.runner.during = stack.delete

    await stack.dispatch(job)

    assert await stack.store.list_runs(job.id) == []


async def test_a_schedule_edit_during_the_run_is_kept_and_the_next_run_follows_it(stack: Stack) -> None:
    job = await stack.create()
    faster = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=60_000, stagger_ms=0)
    stack.runner.during = lambda running: stack.edit(running, schedule=faster)

    started = datetime.now(UTC)
    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.schedule == faster
    assert stored.next_run_at is not None
    assert started + timedelta(seconds=59) <= stored.next_run_at <= datetime.now(UTC) + timedelta(seconds=61)


async def test_other_edits_during_the_run_are_kept(stack: Stack) -> None:
    job = await stack.create()
    stack.runner.during = lambda running: stack.edit(running, name="renamed", prompt="new prompt")

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.name == "renamed" and stored.prompt == "new prompt"


async def test_the_runs_own_fields_survive_adopting_edits_made_during_it(stack: Stack) -> None:
    job = await stack.create(deduplicate=True, delivery=DeliveryConfig(channel="chat"))
    stack.runner.result = JobResult(success=True, output="report")
    stack.runner.during = lambda running: stack.edit(running, name="renamed")

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.name == "renamed" and stored.fire_count == 1 and stored.last_output_hash

    stack.runner.during = None
    await stack.dispatch(job)
    assert stack.delivery.delivered == ["report"]  # the identical second report is held back by the saved hash


async def test_a_run_that_exhausts_its_retries_still_pauses_the_job(stack: Stack) -> None:
    job = await stack.create(max_retries=0)
    stack.runner.result = JobResult(success=False, error="boom")

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.status == JobStatus.PAUSED and stored.consecutive_failures == 1 and stored.next_run_at is None


# ---------------------------------------------------------------------------
# The user acts before the run starts
# ---------------------------------------------------------------------------


async def test_a_job_that_waited_and_was_left_alone_still_runs(stack: Stack, monkeypatch: pytest.MonkeyPatch) -> None:
    job = await stack.create(schedule=STAGGERED)
    _act_during_the_stagger_wait(monkeypatch, _leave_alone)

    await stack.dispatch(job)

    assert len(stack.runner.seen_prompts) == 1 and (await stack.stored(job)).fire_count == 1


async def test_a_pause_during_the_stagger_wait_stops_the_run(stack: Stack, monkeypatch: pytest.MonkeyPatch) -> None:
    job = await stack.create(schedule=STAGGERED)
    _act_during_the_stagger_wait(monkeypatch, lambda: stack.pause(job))

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stack.runner.seen_prompts == [] and stored.status == JobStatus.PAUSED and stored.fire_count == 0


async def test_a_delete_during_the_stagger_wait_stops_the_run(stack: Stack, monkeypatch: pytest.MonkeyPatch) -> None:
    job = await stack.create(schedule=STAGGERED)
    _act_during_the_stagger_wait(monkeypatch, lambda: stack.delete(job))

    await stack.dispatch(job)

    assert stack.runner.seen_prompts == [] and await stack.store.get_job(job.id) is None


async def test_an_edit_during_the_stagger_wait_reaches_the_run(stack: Stack, monkeypatch: pytest.MonkeyPatch) -> None:
    job = await stack.create(schedule=STAGGERED)
    _act_during_the_stagger_wait(monkeypatch, lambda: stack.edit(job, prompt="new prompt"))

    await stack.dispatch(job)

    assert stack.runner.seen_prompts == ["new prompt"]


async def test_a_pause_while_queued_for_a_slot_stops_the_run(stack: Stack) -> None:
    job = await stack.create()
    slot = stack.scheduler._user_sem(USER)
    await slot.acquire()  # the user's only concurrency slot is busy

    dispatched = asyncio.create_task(stack.dispatch(job))
    await _wait_until_parked_on_the_slot(stack, job)
    await stack.pause(job)
    slot.release()
    await dispatched

    stored = await stack.stored(job)
    assert stack.runner.seen_prompts == [] and stored.status == JobStatus.PAUSED and stored.fire_count == 0


# ---------------------------------------------------------------------------
# adopt_latest
# ---------------------------------------------------------------------------


async def test_adopting_copies_everything_but_the_runs_own_fields(stack: Stack) -> None:
    job = await stack.create()
    in_hand = await stack.stored(job)
    in_hand.fire_count, in_hand.last_output_hash = 7, "mine"
    await stack.edit(job, name="renamed", status=JobStatus.PAUSED)

    assert await adopt_latest(stack.store, in_hand) is True

    assert in_hand.name == "renamed" and in_hand.status == JobStatus.PAUSED
    assert in_hand.fire_count == 7 and in_hand.last_output_hash == "mine"


async def test_adopting_reports_a_deleted_job(stack: Stack) -> None:
    job = await stack.create()
    in_hand = await stack.stored(job)
    await stack.delete(job)

    assert await adopt_latest(stack.store, in_hand) is False


def test_the_runs_own_fields_are_fields_of_the_job() -> None:
    assert {f.name for f in fields(CronJob)} >= RUN_OWNED_FIELDS
