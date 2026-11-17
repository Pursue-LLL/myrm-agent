"""What the application hears of a run a crash cut short.

A start turns every marker the previous process left into an interrupted-run record and one counted failure, then
tells the application: the interrupted run goes to the chat the job is bound to as a notice of its own that carries no
error text, and when that failure is the one that paused the job, the pause follows it and names its reason on the
job. Every test drives the real scheduler, executor and recovery over the in-memory store; only the runner and the
lock are stand-ins.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.engine import scheduler as scheduler_module
from myrm_agent_harness.toolkits.cron.engine.recovery import StartupRecovery
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronNotice,
    CronNoticeKind,
    DeliveryConfig,
    JobStatus,
    PauseReason,
)
from tests.support.cron_inflight_stack import CRASHED, STOPPING, InflightStack, make_inflight_stack

INTERRUPTED = CronNotice(kind=CronNoticeKind.RUN_INTERRUPTED, job_name="job job-1", chat_id="chat-7")
PAUSED = CronNotice(kind=CronNoticeKind.JOB_PAUSED_BY_FAILURE, job_name="job job-1")


@pytest.fixture
def stack() -> InflightStack:
    return make_inflight_stack()


@pytest.fixture(autouse=True)
def _no_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the test acts: the scheduler's own timers must never fire."""
    for name in ("_MIN_REFIRE_GAP_S", "_WATCHDOG_INTERVAL_S", "_STARTUP_TICK_DELAY_S"):
        monkeypatch.setattr(scheduler_module, name, 3600.0)


async def test_a_start_announces_a_crashed_run_as_an_interrupted_one_without_the_error_text(
    stack: InflightStack,
) -> None:
    job = await stack.add(due=timedelta(hours=-1), chat_id="chat-7")
    await stack.store.mark_running(job.id)

    await stack.scheduler.start()
    await stack.scheduler.stop()

    assert stack.notices == [INTERRUPTED]
    assert await stack.interrupted() == [("recovery", CRASHED)]


async def test_the_application_hears_of_it_once_the_record_and_the_failure_are_stored(stack: InflightStack) -> None:
    job = await stack.add()
    await stack.store.mark_running(job.id)
    seen: list[tuple[int, list[tuple[str | None, str | None]]]] = []

    async def on_interrupted(_job: CronJob, _paused: bool) -> None:
        seen.append(((await stack.stored()).consecutive_failures, await stack.interrupted()))

    await StartupRecovery(stack.store, AsyncMock(), on_interrupted).report_interrupted(counted=True)

    assert seen == [(1, [("recovery", CRASHED)])]


@pytest.mark.parametrize(
    ("consecutive_failures", "status", "paused"),
    [(1, JobStatus.ACTIVE, False), (2, JobStatus.ACTIVE, True), (2, JobStatus.PAUSED, False)],
    ids=["within the budget", "over the budget", "already paused by the user"],
)
async def test_the_application_is_told_whether_the_crash_paused_the_job(
    stack: InflightStack, consecutive_failures: int, status: JobStatus, paused: bool
) -> None:
    job = await stack.add(consecutive_failures=consecutive_failures, max_retries=2, status=status)
    await stack.store.mark_running(job.id)
    told: list[bool] = []

    async def on_interrupted(_job: CronJob, crash_paused_it: bool) -> None:
        told.append(crash_paused_it)

    await StartupRecovery(stack.store, AsyncMock(), on_interrupted).report_interrupted(counted=True)

    assert told == [paused]
    assert (await stack.stored()).paused_reason == (PauseReason.RUN_FAILURES if paused else None)


async def test_a_crash_that_pauses_the_job_is_announced_after_its_interrupted_run(stack: InflightStack) -> None:
    job = await stack.add(due=timedelta(hours=-1), chat_id="chat-7", consecutive_failures=2, max_retries=2)
    await stack.store.mark_running(job.id)

    await stack.scheduler.start()
    await stack.scheduler.stop()

    stored = await stack.stored()
    assert (stored.status, stored.paused_reason) == (JobStatus.PAUSED, PauseReason.RUN_FAILURES)
    assert stack.notices == [INTERRUPTED, PAUSED]


async def test_a_crash_within_the_failure_budget_leaves_no_pause_reason(stack: InflightStack) -> None:
    job = await stack.add(due=timedelta(hours=-1), consecutive_failures=1, max_retries=2)
    await stack.store.mark_running(job.id)

    await stack.scheduler.start()
    await stack.scheduler.stop()

    stored = await stack.stored()
    assert (stored.consecutive_failures, stored.paused_reason) == (2, None)


async def test_a_crash_that_pauses_a_job_delivering_nowhere_still_announces_the_pause(stack: InflightStack) -> None:
    job = await stack.add(
        due=timedelta(hours=-1), delivery=DeliveryConfig(channel="none"), consecutive_failures=2, max_retries=2
    )
    await stack.store.mark_running(job.id)

    await stack.scheduler.start()
    await stack.scheduler.stop()

    assert stack.notices == [PAUSED]


async def test_a_graceful_stop_leaves_its_record_and_announces_nothing(stack: InflightStack) -> None:
    job = await stack.add(consecutive_failures=2, max_retries=2)
    await stack.launch(job)

    await stack.scheduler.stop()

    assert await stack.interrupted() == [("shutdown", STOPPING)] and stack.notices == []
    assert (await stack.stored()).status == JobStatus.ACTIVE


async def test_a_job_that_delivers_nowhere_is_recorded_but_not_announced(stack: InflightStack) -> None:
    job = await stack.add(due=timedelta(hours=-1), delivery=DeliveryConfig(channel="none"))
    await stack.store.mark_running(job.id)

    await stack.scheduler.start()
    await stack.scheduler.stop()

    assert await stack.interrupted() == [("recovery", CRASHED)] and stack.notices == []
    assert (await stack.stored()).consecutive_failures == 1


async def test_a_deleted_job_is_not_announced(stack: InflightStack) -> None:
    await stack.store.mark_running("gone")

    await stack.scheduler.start()
    await stack.scheduler.stop()

    assert stack.notices == []


async def test_a_callback_that_fails_costs_the_notice_not_the_report(
    stack: InflightStack, caplog: pytest.LogCaptureFixture
) -> None:
    for job_id in ("a", "b"):
        await stack.add(job_id)
        await stack.store.mark_running(job_id)
    announced: list[str] = []

    async def on_interrupted(job: CronJob, _paused: bool) -> None:
        announced.append(job.id)
        raise RuntimeError("no listener")

    with caplog.at_level(logging.WARNING):
        await StartupRecovery(stack.store, AsyncMock(), on_interrupted).report_interrupted(counted=True)

    assert sorted(announced) == ["a", "b"] and await stack.markers() == []
    assert await stack.interrupted("a") == await stack.interrupted("b") == [("recovery", CRASHED)]
    assert "Job a: the interrupted-run notice failed: no listener" in caplog.text
