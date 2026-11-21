"""A cron notice states one fact about a job — a run's outcome, or the scheduler pausing it by itself — and nothing else.

The engine never words or grades a notice: the application layer owns severity and language. Every test drives the
real scheduler and executor over the in-memory store; only the runner, the delivery and the notice callback are
stand-ins.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.cron import CronConfig, CronNoticeCallback, CronScheduler
from myrm_agent_harness.toolkits.cron.engine import run_closer, skipped_runs
from myrm_agent_harness.toolkits.cron.engine.helpers import auto_pause_notice
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronNotice,
    CronNoticeKind,
    DeliveryConfig,
    JobResult,
    JobStatus,
    JobType,
    PauseReason,
    RunStatus,
    Schedule,
    ScheduleKind,
)

EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
ONCE = Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + timedelta(hours=1))

FAILED = JobResult(success=False, error="pump is dry")
# The loop guard's message quotes the call it stopped, and here the call carries transient-error keywords.
BREAKER = JobResult(
    success=False, error="RUNAWAY_CIRCUIT_BREAKER: web_search repeated 5 times (rate limit 429)", circuit_broken=True
)
PAUSED_BY_FAILURE = CronNotice(kind=CronNoticeKind.JOB_PAUSED_BY_FAILURE, job_name="Water the plants")
# A job that delivers nowhere raises no run notice, so a pause notice stands alone.
DELIVERS_NOWHERE = DeliveryConfig(channel="none")


def _job() -> CronJob:
    return CronJob(id="job-1", name="Water the plants", job_type=JobType.AGENT, schedule=EVERY_HOUR, prompt="prompt")


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


class _Runner:
    def __init__(self) -> None:
        self.result = JobResult(success=True, output="done")
        self.runs = 0
        self.during_run: Callable[[CronJob], Awaitable[None]] | None = None

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.runs += 1
        if self.during_run is not None:
            await self.during_run(job)
        return self.result


@dataclass
class Stack:
    store: InMemoryCronStore
    scheduler: CronScheduler
    runner: _Runner
    notices: list[CronNotice] = field(default_factory=list)

    async def dispatch(self, job: CronJob | None = None) -> CronJob:
        """What the timer does for a due job once it is booked: store it and hand the snapshot to the scheduler."""
        job = _job() if job is None else job
        await self.store.save_job(job)
        snapshot = await self.store.get_job(job.id)
        assert snapshot is not None
        await self.scheduler._dispatch(snapshot)
        stored = await self.store.get_job(job.id)
        assert stored is not None
        return stored


def _stack(on_notice: CronNoticeCallback | None) -> Stack:
    store, runner = InMemoryCronStore(), _Runner()
    scheduler = CronScheduler(store, {JobType.AGENT: runner}, _Delivery(), config=CronConfig(), on_notice=on_notice)
    return Stack(store, scheduler, runner)


@pytest.fixture
def stack() -> Stack:
    """A stack whose notice callback records what it receives in ``Stack.notices``."""
    notices: list[CronNotice] = []

    async def record(notice: CronNotice) -> None:
        notices.append(notice)

    return replace(_stack(record), notices=notices)


@pytest.mark.parametrize(
    ("result", "kind", "text"),
    [
        (JobResult(success=True, output="all watered"), CronNoticeKind.RUN_SUCCEEDED, "all watered"),
        (JobResult(success=False, error="pump is dry"), CronNoticeKind.RUN_FAILED, "pump is dry"),
    ],
    ids=["succeeded", "failed"],
)
async def test_a_delivered_run_raises_one_notice_of_its_outcome(
    stack: Stack, result: JobResult, kind: CronNoticeKind, text: str
) -> None:
    stack.runner.result = result

    await stack.dispatch(replace(_job(), chat_id="chat-7"))

    assert stack.notices == [CronNotice(kind=kind, job_name="Water the plants", text=text, chat_id="chat-7")]


async def test_a_run_outcome_snippet_is_cut_to_100_characters(stack: Stack) -> None:
    stack.runner.result = JobResult(success=True, output="x" * 500)

    await stack.dispatch()

    assert stack.notices[0].text == "x" * 100


async def test_a_run_whose_delivery_was_skipped_raises_no_notice(stack: Stack) -> None:
    await stack.dispatch(replace(_job(), delivery=DeliveryConfig(channel="none")))

    assert stack.runner.runs == 1
    assert stack.notices == []


async def test_a_job_past_its_end_time_is_paused_and_says_so(stack: Stack) -> None:
    stored = await stack.dispatch(replace(_job(), expires_at=datetime.now(UTC) - timedelta(minutes=1)))

    assert stored.status == JobStatus.PAUSED and stack.runner.runs == 0
    assert stack.notices == [CronNotice(kind=CronNoticeKind.JOB_EXPIRED, job_name="Water the plants")]


async def test_a_job_at_its_fire_limit_is_paused_and_says_so(stack: Stack) -> None:
    stored = await stack.dispatch(replace(_job(), max_fires=3, fire_count=3))

    assert stored.status == JobStatus.PAUSED and stack.runner.runs == 0
    assert stack.notices == [
        CronNotice(kind=CronNoticeKind.JOB_MAX_FIRES_REACHED, job_name="Water the plants", max_fires=3)
    ]


async def test_a_skip_that_pauses_nothing_raises_no_notice(stack: Stack) -> None:
    stored = await stack.dispatch(replace(_job(), cooldown_seconds=3600, last_run_at=datetime.now(UTC)))

    assert stored.status == JobStatus.ACTIVE and stack.runner.runs == 0
    assert stack.notices == []


async def test_the_pause_notice_follows_the_failed_run_that_caused_it(stack: Stack) -> None:
    stack.runner.result = FAILED

    stored = await stack.dispatch(replace(_job(), consecutive_failures=2, chat_id="chat-7"))

    assert stored.status == JobStatus.PAUSED
    assert [notice.kind for notice in stack.notices] == [
        CronNoticeKind.RUN_FAILED,
        CronNoticeKind.JOB_PAUSED_BY_FAILURE,
    ]
    assert stack.notices[1] == PAUSED_BY_FAILURE


async def test_a_circuit_break_is_announced_by_the_pause_it_causes_alone(stack: Stack) -> None:
    stack.runner.result = BREAKER

    stored = await stack.dispatch(replace(_job(), chat_id="chat-7"))

    assert stored.status == JobStatus.PAUSED
    assert stack.notices == [PAUSED_BY_FAILURE]


@pytest.mark.parametrize(
    ("schedule", "consecutive_failures", "result", "reason"),
    [
        (EVERY_HOUR, 2, FAILED, PauseReason.RUN_FAILURES),
        (EVERY_HOUR, 0, BREAKER, PauseReason.CIRCUIT_BREAK),
        (ONCE, 0, FAILED, PauseReason.RUN_FAILURES),
        (ONCE, 0, BREAKER, PauseReason.CIRCUIT_BREAK),
    ],
    ids=["third consecutive failure", "circuit break", "one-time failure", "one-time circuit break"],
)
async def test_a_run_that_pauses_its_job_names_why_and_says_so_even_when_the_job_delivers_nowhere(
    stack: Stack, schedule: Schedule, consecutive_failures: int, result: JobResult, reason: PauseReason
) -> None:
    stack.runner.result = result
    job = replace(_job(), schedule=schedule, consecutive_failures=consecutive_failures, delivery=DELIVERS_NOWHERE)

    stored = await stack.dispatch(job)

    assert stored.status == JobStatus.PAUSED and stored.next_run_at is None
    assert stored.paused_reason == reason
    assert stack.notices == [PAUSED_BY_FAILURE]


@pytest.mark.parametrize(
    ("schedule", "result"),
    [
        (EVERY_HOUR, FAILED),
        (EVERY_HOUR, JobResult(success=True, output="done")),
        (ONCE, JobResult(success=False, error="429 too many requests")),
    ],
    ids=["first failure retried with backoff", "success", "one-time transient failure retried"],
)
async def test_a_run_that_leaves_its_job_active_raises_no_pause_notice(
    stack: Stack, schedule: Schedule, result: JobResult
) -> None:
    stack.runner.result = result

    stored = await stack.dispatch(replace(_job(), schedule=schedule, delivery=DELIVERS_NOWHERE))

    assert stored.status == JobStatus.ACTIVE
    assert stack.notices == []


async def test_a_job_the_user_paused_during_the_run_raises_no_pause_notice(stack: Stack) -> None:
    async def pause_it(running: CronJob) -> None:
        latest = await stack.store.get_job(running.id)
        assert latest is not None
        await stack.store.save_job(replace(latest, status=JobStatus.PAUSED))

    stack.runner.result = FAILED
    stack.runner.during_run = pause_it

    stored = await stack.dispatch(replace(_job(), consecutive_failures=2, delivery=DELIVERS_NOWHERE))

    assert (stored.status, stored.paused_reason) == (JobStatus.PAUSED, None)
    assert stack.notices == []


def _unparsable(*args: object, **kwargs: object) -> datetime:
    raise ValueError("unparsable schedule")


async def test_a_schedule_that_cannot_be_computed_pauses_its_job_at_once_and_says_so(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_closer, "next_eligible_run", _unparsable)

    stored = await stack.dispatch(replace(_job(), delivery=DELIVERS_NOWHERE))

    assert stored.status == JobStatus.PAUSED and stored.next_run_at is None
    assert stored.paused_reason == PauseReason.SCHEDULE_ERROR
    assert stored.last_status == RunStatus.OK
    assert stored.last_error == "Schedule error: unparsable schedule"
    assert stack.notices == [PAUSED_BY_FAILURE]


async def test_a_skipped_run_whose_schedule_cannot_be_computed_pauses_its_job_and_says_so(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(skipped_runs, "next_eligible_run", _unparsable)

    stored = await stack.dispatch(replace(_job(), cooldown_seconds=3600, last_run_at=datetime.now(UTC)))

    assert stack.runner.runs == 0
    assert stored.status == JobStatus.PAUSED and stored.next_run_at is None
    assert stored.paused_reason == PauseReason.SCHEDULE_ERROR
    assert stored.last_error == "Schedule error: unparsable schedule"
    assert stack.notices == [PAUSED_BY_FAILURE]


async def test_a_skipped_run_of_a_job_the_user_paused_raises_no_pause_notice(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(skipped_runs, "next_eligible_run", _unparsable)
    job = replace(_job(), status=JobStatus.PAUSED, cooldown_seconds=3600, last_run_at=datetime.now(UTC))

    stored = await stack.dispatch(job)

    assert stored.status == JobStatus.PAUSED
    assert stack.notices == []


async def test_a_one_time_circuit_break_is_paused_and_recorded_as_one_not_retried(stack: Stack) -> None:
    stack.runner.result = BREAKER

    stored = await stack.dispatch(replace(_job(), schedule=ONCE, delivery=DELIVERS_NOWHERE))

    assert stored.status == JobStatus.PAUSED and stored.next_run_at is None
    assert stored.last_status == RunStatus.CIRCUIT_BREAK
    assert stored.last_error == BREAKER.error


async def test_a_notice_callback_that_raises_fails_neither_the_run_nor_the_pause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def failing(notice: CronNotice) -> None:
        raise RuntimeError("bus is down")

    stack = _stack(failing)
    with caplog.at_level(logging.WARNING):
        ran = await stack.dispatch()
        paused = await stack.dispatch(replace(_job(), max_fires=1, fire_count=1))
        stack.runner.result = FAILED
        failed = await stack.dispatch(replace(_job(), consecutive_failures=2))

    assert ran.last_status == RunStatus.OK
    assert paused.status == JobStatus.PAUSED
    assert failed.status == JobStatus.PAUSED
    assert "was not delivered: bus is down" in caplog.text


async def test_a_scheduler_without_a_notice_callback_runs_and_pauses_normally() -> None:
    stack = _stack(None)

    ran = await stack.dispatch()
    paused = await stack.dispatch(replace(_job(), max_fires=1, fire_count=1))
    stack.runner.result = FAILED
    failed = await stack.dispatch(replace(_job(), consecutive_failures=2))

    assert ran.last_status == RunStatus.OK
    assert paused.status == JobStatus.PAUSED
    assert failed.status == JobStatus.PAUSED


@pytest.mark.parametrize(
    ("skip_reason", "kind", "max_fires"),
    [("expired", CronNoticeKind.JOB_EXPIRED, None), ("max_fires_reached", CronNoticeKind.JOB_MAX_FIRES_REACHED, 5)],
)
def test_a_pausing_verdict_maps_to_its_notice(skip_reason: str, kind: CronNoticeKind, max_fires: int | None) -> None:
    job = replace(_job(), name="n", max_fires=5)

    assert auto_pause_notice(job, skip_reason) == CronNotice(kind=kind, job_name="n", max_fires=max_fires)


@pytest.mark.parametrize("skip_reason", ["cooldown_active", "anything-else"])
def test_a_verdict_that_pauses_nothing_has_no_notice(skip_reason: str) -> None:
    assert auto_pause_notice(_job(), skip_reason) is None
