"""Unit tests for CronManager reads and state changes: queries, delete, pause, resume and manual trigger."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.types import JobStatus
from tests.support.cron_manager_mocks import make_job, make_manager

# ---------------------------------------------------------------------------
# Query methods
# ---------------------------------------------------------------------------


class TestQueryMethods:
    @pytest.mark.asyncio
    async def test_list_jobs(self) -> None:
        mgr = make_manager()
        jobs = [make_job()]
        mgr._store.list_jobs = AsyncMock(return_value=jobs)
        result = await mgr.list_jobs(limit=10, offset=0)
        assert result == jobs
        mgr._store.list_jobs.assert_awaited_once_with(
            name_filter=None, chat_id=None, project_id=None, include_system=False, limit=10, offset=0
        )

    @pytest.mark.asyncio
    async def test_list_jobs_hands_a_request_for_system_jobs_to_the_store(self) -> None:
        mgr = make_manager()
        mgr._store.list_jobs = AsyncMock(return_value=[])
        await mgr.list_jobs(include_system=True)
        assert mgr._store.list_jobs.await_args.kwargs["include_system"] is True

    @pytest.mark.asyncio
    async def test_count_jobs(self) -> None:
        mgr = make_manager()
        mgr._store.count_jobs = AsyncMock(return_value=5)
        assert await mgr.count_jobs() == 5
        mgr._store.count_jobs.assert_awaited_once_with(
            name_filter=None, chat_id=None, project_id=None, include_system=False
        )

    @pytest.mark.asyncio
    async def test_get_job_found(self) -> None:
        mgr = make_manager()
        job = make_job()
        mgr._store.get_job = AsyncMock(return_value=job)
        assert await mgr.get_job("job-1") == job

    @pytest.mark.asyncio
    async def test_get_job_not_found(self) -> None:
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=None)
        assert await mgr.get_job("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_runs_with_missing_job_returns_empty(self) -> None:
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=None)
        result = await mgr.list_runs(job_id="job-1")
        assert result == []
        mgr._store.list_runs.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_runs_with_existing_job_delegates_to_store(self) -> None:
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=make_job())
        await mgr.list_runs(job_id="job-1", limit=5, offset=10, status="failed")
        mgr._store.list_runs.assert_awaited_once_with("job-1", limit=5, offset=10, status="failed")

    @pytest.mark.asyncio
    async def test_list_runs_without_job_id(self) -> None:
        mgr = make_manager()
        await mgr.list_runs()
        mgr._store.list_runs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_count_runs_with_missing_job_returns_zero(self) -> None:
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=None)
        result = await mgr.count_runs(job_id="job-1")
        assert result == 0
        mgr._store.count_runs.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_count_runs_without_job_id(self) -> None:
        mgr = make_manager()
        mgr._store.count_runs = AsyncMock(return_value=3)
        result = await mgr.count_runs()
        assert result == 3

    @pytest.mark.asyncio
    async def test_get_monitor_state(self) -> None:
        mgr = make_manager()
        await mgr.get_monitor_state("job-1")
        mgr._store.get_monitor_state.assert_awaited_once_with("job-1")

    @pytest.mark.asyncio
    async def test_batch_get_monitor_states(self) -> None:
        mgr = make_manager()
        await mgr.batch_get_monitor_states(["job-1", "job-2"])
        mgr._store.batch_get_monitor_states.assert_awaited_once_with(["job-1", "job-2"])


# ---------------------------------------------------------------------------
# delete_job
# ---------------------------------------------------------------------------


class TestDeleteJob:
    @pytest.mark.asyncio
    async def test_delete_success(self) -> None:
        mgr = make_manager()
        job = make_job()
        mgr._store.get_job = AsyncMock(return_value=job)
        assert await mgr.delete_job("job-1") is True
        mgr._store.delete_job_cascade.assert_awaited_once_with("job-1")
        mgr._scheduler.notify_change.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self) -> None:
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=None)
        assert await mgr.delete_job("nonexistent") is False


# ---------------------------------------------------------------------------
# pause / resume / trigger_now
# ---------------------------------------------------------------------------


class TestPauseResumeTrigger:
    @pytest.mark.asyncio
    async def test_pause_job(self) -> None:
        mgr = make_manager()
        job = make_job()
        mgr._store.get_job = AsyncMock(return_value=job)
        result = await mgr.pause_job("job-1")
        assert result is not None
        assert result.status == JobStatus.PAUSED

    @pytest.mark.asyncio
    async def test_resume_job(self) -> None:
        mgr = make_manager()
        job = make_job(status=JobStatus.PAUSED, consecutive_failures=5)
        mgr._store.get_job = AsyncMock(return_value=job)
        result = await mgr.resume_job("job-1")
        assert result is not None
        assert result.status == JobStatus.ACTIVE
        assert result.consecutive_failures == 0
        assert result.next_run_at is not None

    @pytest.mark.asyncio
    async def test_resume_job_not_found(self) -> None:
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=None)
        assert await mgr.resume_job("job-1") is None
        mgr._store.save_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trigger_now(self) -> None:
        mgr = make_manager()
        job = make_job(status=JobStatus.ACTIVE)
        mgr._store.get_job = AsyncMock(return_value=job)
        assert await mgr.trigger_now("job-1") is True
        mgr._store.save_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_trigger_now_paused_job(self) -> None:
        mgr = make_manager()
        job = make_job(status=JobStatus.PAUSED)
        mgr._store.get_job = AsyncMock(return_value=job)
        assert await mgr.trigger_now("job-1") is False

    @pytest.mark.asyncio
    async def test_trigger_now_job_not_found(self) -> None:
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=None)
        assert await mgr.trigger_now("job-1") is False
        mgr._store.save_job.assert_not_awaited()
