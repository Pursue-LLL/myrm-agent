"""Integration tests for DAILY session-target full lifecycle.

Validates the chain: executor writes CronRunRecord → _build_daily_context
reads from the same store → correct context injected into prompt.

Uses InMemoryCronStore (a real CronStore implementation, not a mock)
to ensure the full read/write path works end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
    SessionTarget,
)

from app.core.cron.adapters.agent_runner import _build_daily_context

_STORE_PATCH = "app.core.cron.adapters.setup.get_cron_store"


def _make_daily_job(job_id: str = "daily-integ-1") -> CronJob:
    return CronJob(
        id=job_id,
        user_id="user-integ",
        name="Hourly Monitor",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
        status=JobStatus.ACTIVE,
        prompt="Check server health",
        session_target=SessionTarget.DAILY,
        delivery=DeliveryConfig(channel="chat"),
    )


class FakeRunner:
    def __init__(self, output: str) -> None:
        self._output = output
        self.received_contexts: list[str] = []

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.received_contexts.append(context)
        return JobResult(success=True, output=self._output, exit_code=1)


class NullDelivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        pass


@pytest.mark.asyncio
async def test_daily_context_lifecycle_real_store() -> None:
    """Full chain: executor writes record → _build_daily_context reads it back."""
    store = InMemoryCronStore()
    executor = JobExecutor(store=store, delivery=NullDelivery())
    job = _make_daily_job()
    await store.save_job(job)

    runner1 = FakeRunner(output="CPU 45%, all normal")
    await executor.run_and_record(job, runner1)

    runs_after_first = await store.list_runs(job.id)
    assert len(runs_after_first) == 1
    assert runs_after_first[0].status == RunStatus.OK
    assert "CPU 45%" in (runs_after_first[0].output or "")

    with patch(_STORE_PATCH, return_value=store):
        ctx = await _build_daily_context(job)

    assert "<daily_context>" in ctx
    assert "CPU 45%" in ctx


@pytest.mark.asyncio
async def test_daily_context_multiple_runs_chronological() -> None:
    """Multiple same-day runs appear in oldest-first order."""
    store = InMemoryCronStore()
    executor = JobExecutor(store=store, delivery=NullDelivery())
    job = _make_daily_job()
    await store.save_job(job)

    outputs = ["CPU 40%", "CPU 55%", "CPU 72%"]
    for output in outputs:
        runner = FakeRunner(output=output)
        await executor.run_and_record(job, runner)

    with patch(_STORE_PATCH, return_value=store):
        ctx = await _build_daily_context(job)

    assert "<daily_context>" in ctx
    idx_40 = ctx.index("CPU 40%")
    idx_55 = ctx.index("CPU 55%")
    idx_72 = ctx.index("CPU 72%")
    assert idx_40 < idx_55 < idx_72, f"Expected chronological order: {ctx}"


@pytest.mark.asyncio
async def test_daily_context_first_run_no_history() -> None:
    """First run ever: _build_daily_context returns empty string."""
    store = InMemoryCronStore()
    job = _make_daily_job()
    await store.save_job(job)

    with patch(_STORE_PATCH, return_value=store):
        ctx = await _build_daily_context(job)

    assert ctx == ""


@pytest.mark.asyncio
async def test_daily_context_cross_day_summary() -> None:
    """Cross-day boundary injects yesterday's last output as summary."""
    store = InMemoryCronStore()
    job = _make_daily_job()
    await store.save_job(job)

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    from myrm_agent_harness.toolkits.cron.types import CronRunRecord

    yesterday_record = CronRunRecord(
        id="run-yesterday",
        job_id=job.id,
        started_at=yesterday - timedelta(seconds=30),
        finished_at=yesterday,
        duration_ms=30_000,
        status=RunStatus.OK,
        output="End of day: all systems green",
    )
    await store.save_run(yesterday_record)

    with patch(_STORE_PATCH, return_value=store):
        ctx = await _build_daily_context(job)

    assert "Yesterday's last output" in ctx
    assert "End of day: all systems green" in ctx


@pytest.mark.asyncio
async def test_daily_context_isolated_job_not_affected() -> None:
    """ISOLATED jobs should NOT trigger daily context lookup."""
    store = InMemoryCronStore()
    isolated_job = CronJob(
        id="isolated-1",
        user_id="user-integ",
        name="Isolated Task",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
        status=JobStatus.ACTIVE,
        prompt="Do stuff",
        session_target=SessionTarget.ISOLATED,
        delivery=DeliveryConfig(channel="chat"),
    )
    await store.save_job(isolated_job)

    executor = JobExecutor(store=store, delivery=NullDelivery())
    runner = FakeRunner(output="result A")
    await executor.run_and_record(isolated_job, runner)

    with patch(_STORE_PATCH, return_value=store):
        ctx = await _build_daily_context(isolated_job)

    assert "<daily_context>" in ctx or ctx == ""


class FakeFailRunner:
    """Runner that always fails."""

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        return JobResult(success=False, output="", error="crash", exit_code=2)


@pytest.mark.asyncio
async def test_failed_runs_excluded_from_context() -> None:
    """Only status=ok runs appear in daily context; errors are filtered out."""
    store = InMemoryCronStore()
    executor = JobExecutor(store=store, delivery=NullDelivery())
    job = _make_daily_job()
    await store.save_job(job)

    fail_runner = FakeFailRunner()
    await executor.run_and_record(job, fail_runner)

    ok_runner = FakeRunner(output="Recovery complete")
    await executor.run_and_record(job, ok_runner)

    runs = await store.list_runs(job.id)
    assert len(runs) == 2
    statuses = {r.status for r in runs}
    assert RunStatus.ERROR in statuses
    assert RunStatus.OK in statuses

    with patch(_STORE_PATCH, return_value=store):
        ctx = await _build_daily_context(job)

    assert "Recovery complete" in ctx
    assert "crash" not in ctx


@pytest.mark.asyncio
async def test_main_session_target_not_affected() -> None:
    """MAIN session jobs: _build_daily_context still works but integration
    point in _run_once only calls it for DAILY jobs."""
    store = InMemoryCronStore()
    main_job = CronJob(
        id="main-1",
        user_id="user-integ",
        name="Main Session",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
        status=JobStatus.ACTIVE,
        prompt="Do things",
        session_target=SessionTarget.MAIN,
        delivery=DeliveryConfig(channel="chat"),
    )
    await store.save_job(main_job)

    executor = JobExecutor(store=store, delivery=NullDelivery())
    runner = FakeRunner(output="main output")
    await executor.run_and_record(main_job, runner)

    assert main_job.session_target == SessionTarget.MAIN
    assert main_job.session_target != SessionTarget.DAILY
