"""What closing a one-shot run leaves on its job and on its run record.

The executor deletes a one-time job after a successful run only when ``delete_after_run`` is set and the delivery did
not fail. A failed delivery leaves the job completed, with the run recorded as ok and its delivery as failed: they hold
the only copy of the result. A retry that succeeds leaves no error on the completed job; the failed attempt stays in its
run record. These scenarios run the real executor over the in-memory store; only the runner and the delivery are
stand-ins.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    DeliveryStatus,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

_RATE_LIMITED = "HTTP 429: rate limit exceeded"  # a transient error: a one-shot that fails with it is retried


class _Runner:
    """Plays the scripted results one run at a time; a runner without a script always succeeds."""

    def __init__(self, *script: JobResult) -> None:
        self._script = list(script)

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        return self._script.pop(0) if self._script else JobResult(success=True, output="the reminder text")


class _Delivery:
    def __init__(self, *, fails: bool) -> None:
        self._fails = fails

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        if self._fails:
            raise RuntimeError("webhook returned HTTP 500")


async def _stored_once_job(*, delete_after_run: bool, channel: str = "chat") -> tuple[InMemoryCronStore, CronJob]:
    store = InMemoryCronStore()
    job = CronJob(
        id="reminder",
        name="reminder",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + timedelta(hours=1)),
        prompt="remind me",
        delivery=DeliveryConfig(channel=channel),
        delete_after_run=delete_after_run,
    )
    await store.save_job(job)
    return store, job


async def _run_once_job(
    *, delivery_fails: bool, delete_after_run: bool, channel: str = "chat"
) -> tuple[InMemoryCronStore, CronJob]:
    store, job = await _stored_once_job(delete_after_run=delete_after_run, channel=channel)
    executor = JobExecutor(store=store, delivery=_Delivery(fails=delivery_fails))
    await executor.run_and_record(job, _Runner())
    return store, job


class TestDeletionOfAOneShot:
    async def test_a_failed_delivery_keeps_the_job_completed(self) -> None:
        store, job = await _run_once_job(delivery_fails=True, delete_after_run=True)

        kept = await store.get_job(job.id)
        assert kept is not None
        assert kept.status == JobStatus.COMPLETED
        assert kept.next_run_at is None
        assert kept.last_status == RunStatus.OK

        (run,) = await store.list_runs(job.id)
        assert run.status == RunStatus.OK
        assert run.output == "the reminder text"
        assert run.delivery_status == DeliveryStatus.FAILED
        assert "HTTP 500" in (run.delivery_error or "")

    async def test_a_delivered_reminder_is_deleted(self) -> None:
        store, job = await _run_once_job(delivery_fails=False, delete_after_run=True)
        assert await store.get_job(job.id) is None

    async def test_a_run_that_attempted_no_delivery_is_deleted(self) -> None:
        store, job = await _run_once_job(delivery_fails=True, delete_after_run=True, channel="none")
        assert await store.get_job(job.id) is None

    @pytest.mark.parametrize("delivery_fails", [False, True], ids=["delivered", "delivery_failed"])
    async def test_without_delete_after_run_the_job_completes_either_way(self, delivery_fails: bool) -> None:
        store, job = await _run_once_job(delivery_fails=delivery_fails, delete_after_run=False)
        kept = await store.get_job(job.id)
        assert kept is not None
        assert kept.status == JobStatus.COMPLETED


class TestErrorOfAOneShot:
    async def test_a_retry_that_succeeds_leaves_no_error_on_the_job(self) -> None:
        store, job = await _stored_once_job(delete_after_run=False)
        executor = JobExecutor(store=store, delivery=_Delivery(fails=False))
        runner = _Runner(JobResult(success=False, error=_RATE_LIMITED))

        await executor.run_and_record(job, runner)

        waiting = await store.get_job(job.id)
        assert waiting is not None
        assert waiting.status == JobStatus.ACTIVE
        assert waiting.last_error == _RATE_LIMITED

        await executor.run_and_record(waiting, runner)

        done = await store.get_job(job.id)
        assert done is not None
        assert done.status == JobStatus.COMPLETED
        assert done.last_status == RunStatus.OK
        assert done.last_error is None
        assert [run.error for run in await store.list_runs(job.id) if run.status == RunStatus.ERROR] == [_RATE_LIMITED]
