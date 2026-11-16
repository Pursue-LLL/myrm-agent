"""A one-shot whose delivery failed keeps its job and its run record: they hold the only copy of the result.

The executor deletes a one-time job after a successful run only when ``delete_after_run`` is set and the delivery did
not fail. A failed delivery leaves the job completed, with the run recorded as ok and its delivery as failed. These
scenarios run the real executor over the in-memory store; only the runner and the delivery are stand-ins.
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


class _Runner:
    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        return JobResult(success=True, output="the reminder text")


class _Delivery:
    def __init__(self, *, fails: bool) -> None:
        self._fails = fails

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        if self._fails:
            raise RuntimeError("webhook returned HTTP 500")


async def _run_once_job(
    *, delivery_fails: bool, delete_after_run: bool, channel: str = "chat"
) -> tuple[InMemoryCronStore, CronJob]:
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
