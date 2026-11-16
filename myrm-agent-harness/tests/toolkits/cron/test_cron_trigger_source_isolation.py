"""A run's trigger source belongs to that run: runs of one executor overlap and must not read each other's."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronRunRecord,
    DeliveryConfig,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)


def _job(job_id: str) -> CronJob:
    return CronJob(
        id=job_id,
        name=job_id,
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
        status=JobStatus.ACTIVE,
        prompt="p",
        delivery=DeliveryConfig(channel="none"),
        next_run_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _Runner:
    """Answers with ``result`` once ``gate`` opens, so a second run can overlap this one."""

    def __init__(self, result: JobResult, gate: asyncio.Event | None = None) -> None:
        self._result = result
        self._gate = gate

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        if self._gate is not None:
            await self._gate.wait()
        return self._result


def _executor() -> tuple[JobExecutor, list[CronRunRecord]]:
    saved: list[CronRunRecord] = []
    store = AsyncMock()
    store.save_job = AsyncMock(side_effect=lambda j: j)
    store.save_run = AsyncMock(side_effect=saved.append)
    store.get_job = AsyncMock(side_effect=_job)
    store.get_latest_integrity_hash = AsyncMock(return_value=None)
    return JobExecutor(store=store, delivery=AsyncMock()), saved


_SKIPPED = JobResult(success=True, skipped=True, skip_reason="nothing new")
_DEFERRED = JobResult(success=False, error="busy", retry_at=datetime.now(UTC) + timedelta(minutes=5))


@pytest.mark.parametrize("slow_result", [_SKIPPED, _DEFERRED], ids=["skipped-by-runner", "deferred"])
async def test_overlapping_run_does_not_rewrite_the_trigger_source_of_a_skipped_run(slow_result: JobResult) -> None:
    executor, saved = _executor()
    gate = asyncio.Event()

    slow = asyncio.create_task(executor.run_and_record(_job("slow"), _Runner(slow_result, gate), trigger_source="cron"))
    await asyncio.sleep(0)  # the slow run is now parked inside its runner
    await executor.run_and_record(_job("fast"), _Runner(JobResult(success=True)), trigger_source="manual")
    gate.set()
    await slow

    by_job = {run.job_id: run for run in saved}
    assert by_job["slow"].status == RunStatus.SKIPPED
    assert by_job["slow"].trigger_source == "cron"
    assert by_job["fast"].trigger_source == "manual"


async def test_overlapping_run_does_not_rewrite_the_trigger_source_of_a_probe_skip() -> None:
    executor, saved = _executor()
    gate = asyncio.Event()

    async def evaluate(job: CronJob) -> tuple[bool, str | None]:
        if job.id == "slow":
            await gate.wait()
            return False, None
        return True, None

    probe = AsyncMock()
    probe.evaluate = AsyncMock(side_effect=evaluate)
    executor._pre_condition = probe
    slow_job, fast_job = _job("slow"), _job("fast")
    slow_job.pre_condition_script = fast_job.pre_condition_script = "true"

    slow = asyncio.create_task(
        executor.run_and_record(slow_job, _Runner(JobResult(success=True)), trigger_source="cron")
    )
    await asyncio.sleep(0)
    await executor.run_and_record(fast_job, _Runner(JobResult(success=True)), trigger_source="webhook")
    gate.set()
    await slow

    by_job = {run.job_id: run for run in saved}
    assert by_job["slow"].status == RunStatus.SKIPPED
    assert by_job["slow"].trigger_source == "cron"
    assert by_job["fast"].trigger_source == "webhook"
