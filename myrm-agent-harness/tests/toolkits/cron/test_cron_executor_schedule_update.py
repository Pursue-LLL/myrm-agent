"""Unit tests for how JobExecutor updates a job's state and schedule after a run."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.types import (
    JobResult,
    JobStatus,
    RunStatus,
    ScheduleKind,
)
from tests.support.cron_executor_mocks import make_executor, make_job, make_schedule

# ---------------------------------------------------------------------------
# _update_after_run — recurring jobs
# ---------------------------------------------------------------------------


class TestUpdateAfterRunRecurring:
    @pytest.mark.asyncio
    async def test_success_schedules_next(self) -> None:
        executor, store, _ = make_executor()
        job = make_job(consecutive_failures=2)
        result = JobResult(success=True, output="ok")
        now = datetime.now(UTC)
        await executor._update_after_run(job, result, 0, now)
        assert job.next_run_at is not None
        assert job.last_status == RunStatus.OK
        assert job.consecutive_failures == 0
        assert job.last_failure_alert_at is None
        store.save_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failure_within_retries_uses_backoff(self) -> None:
        executor, _store, _ = make_executor()
        job = make_job(max_retries=3)
        result = JobResult(success=False, error="oops")
        now = datetime.now(UTC)
        await executor._update_after_run(job, result, 1, now)
        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at is not None
        assert job.next_run_at > now
        assert job.last_status == RunStatus.ERROR

    @pytest.mark.asyncio
    async def test_failure_exceeds_retries_pauses(self) -> None:
        executor, _store, _ = make_executor()
        job = make_job(max_retries=2)
        result = JobResult(success=False, error="persistent error")
        now = datetime.now(UTC)
        await executor._update_after_run(job, result, 3, now)
        assert job.status == JobStatus.PAUSED
        assert job.next_run_at is None

    @pytest.mark.asyncio
    async def test_deleted_job_skips_update(self) -> None:
        """Job deleted during execution: _update_after_run should silently skip."""
        executor, store, _ = make_executor()
        store.get_job = AsyncMock(return_value=None)
        job = make_job()
        result = JobResult(success=True, output="ok")
        await executor._update_after_run(job, result, 0, datetime.now(UTC))
        store.save_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deleted_once_job_skips_update(self) -> None:
        """One-shot job deleted during execution: should silently skip."""
        executor, store, _ = make_executor()
        store.get_job = AsyncMock(return_value=None)
        job = make_job(schedule=make_schedule(ScheduleKind.ONCE))
        result = JobResult(success=True, output="done")
        await executor._update_after_run(job, result, 0, datetime.now(UTC))
        store.save_job.assert_not_awaited()
        store.delete_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_job_store_error_propagates(self) -> None:
        """Store failure on get_job should propagate, not be swallowed."""
        executor, store, _ = make_executor()
        store.get_job = AsyncMock(side_effect=RuntimeError("db connection lost"))
        job = make_job()
        result = JobResult(success=True, output="ok")
        with pytest.raises(RuntimeError, match="db connection lost"):
            await executor._update_after_run(job, result, 0, datetime.now(UTC))
        store.save_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deleted_failed_job_skips_update(self) -> None:
        """Failed job deleted during execution: should skip (no resurrection)."""
        executor, store, _ = make_executor()
        store.get_job = AsyncMock(return_value=None)
        job = make_job(max_retries=3)
        result = JobResult(success=False, error="error")
        await executor._update_after_run(job, result, 1, datetime.now(UTC))
        store.save_job.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_once_completion
# ---------------------------------------------------------------------------


class TestHandleOnceCompletion:
    @pytest.mark.asyncio
    async def test_success_delete_after_run(self) -> None:
        executor, store, _ = make_executor()
        job = make_job(
            schedule=make_schedule(ScheduleKind.ONCE),
            delete_after_run=True,
        )
        result = JobResult(success=True, output="done")
        await executor._handle_once_completion(job, result, 0, datetime.now(UTC))
        store.delete_job.assert_awaited_once_with("job-1")

    @pytest.mark.asyncio
    async def test_success_no_delete(self) -> None:
        executor, store, _ = make_executor()
        job = make_job(
            schedule=make_schedule(ScheduleKind.ONCE),
            delete_after_run=False,
        )
        result = JobResult(success=True, output="done")
        await executor._handle_once_completion(job, result, 0, datetime.now(UTC))
        assert job.status == JobStatus.COMPLETED
        assert job.next_run_at is None
        store.save_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transient_error_retries(self) -> None:
        executor, _store, _ = make_executor()
        job = make_job(
            schedule=make_schedule(ScheduleKind.ONCE),
            max_retries=3,
        )
        result = JobResult(success=False, error="rate limit exceeded")
        now = datetime.now(UTC)
        await executor._handle_once_completion(job, result, 1, now)
        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at is not None
        assert job.next_run_at > now

    @pytest.mark.asyncio
    async def test_permanent_error_pauses(self) -> None:
        executor, _store, _ = make_executor()
        job = make_job(
            schedule=make_schedule(ScheduleKind.ONCE),
            max_retries=2,
        )
        result = JobResult(success=False, error="some permanent error xyz")
        now = datetime.now(UTC)
        await executor._handle_once_completion(job, result, 3, now)
        assert job.status == JobStatus.PAUSED
        assert job.next_run_at is None


# ---------------------------------------------------------------------------
# _handle_schedule_compute_error
# ---------------------------------------------------------------------------


class TestHandleScheduleComputeError:
    def test_below_threshold_sets_fallback(self) -> None:
        executor, _, _ = make_executor()
        job = make_job(consecutive_failures=0)
        finished = datetime.now(UTC)
        executor._handle_schedule_compute_error(job, ValueError("bad cron"), finished)
        assert job.status == JobStatus.ACTIVE
        assert job.consecutive_failures == 1
        assert job.next_run_at is not None
        assert job.next_run_at == finished + timedelta(seconds=60)

    def test_at_threshold_pauses(self) -> None:
        executor, _, _ = make_executor()
        job = make_job(consecutive_failures=2)
        finished = datetime.now(UTC)
        executor._handle_schedule_compute_error(job, ValueError("bad cron"), finished)
        assert job.status == JobStatus.PAUSED
        assert job.next_run_at is None
