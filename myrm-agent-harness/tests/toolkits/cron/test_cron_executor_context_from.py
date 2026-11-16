"""Unit tests for how JobExecutor resolves a job's ``context_from`` references into runner context."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
)
from tests.support.cron_executor_mocks import make_executor, make_job

# ---------------------------------------------------------------------------
# _resolve_context_from tests
# ---------------------------------------------------------------------------


class TestResolveContextFrom:
    """Tests for _resolve_context_from: cross-job context injection."""

    @pytest.mark.asyncio
    async def test_empty_context_from_returns_empty(self) -> None:
        """Job with no context_from should produce empty string."""
        executor, _store, _delivery = make_executor()
        job = make_job(context_from=())
        result = await executor._resolve_context_from(job)
        assert result == ""

    @pytest.mark.asyncio
    async def test_single_ref_with_output(self) -> None:
        """Single ref with a successful run injects its output."""
        executor, store, _delivery = make_executor()
        ref_job = make_job(id="ref-1", name="Stock Monitor")
        run = MagicMock()
        run.output = "AAPL: 150.3"
        store.list_runs = AsyncMock(return_value=[run])
        store.get_job = AsyncMock(return_value=ref_job)

        job = make_job(context_from=("ref-1",))
        result = await executor._resolve_context_from(job)
        assert "Stock Monitor" in result
        assert "AAPL: 150.3" in result

    @pytest.mark.asyncio
    async def test_ref_with_no_successful_runs_skipped(self) -> None:
        """Ref whose latest runs are empty is silently skipped."""
        executor, store, _delivery = make_executor()
        store.list_runs = AsyncMock(return_value=[])

        job = make_job(context_from=("ref-missing-runs",))
        result = await executor._resolve_context_from(job)
        assert result == ""

    @pytest.mark.asyncio
    async def test_ref_with_empty_output_skipped(self) -> None:
        """Ref whose run has None/empty output is skipped."""
        executor, store, _delivery = make_executor()
        run = MagicMock()
        run.output = ""
        store.list_runs = AsyncMock(return_value=[run])

        job = make_job(context_from=("ref-empty",))
        result = await executor._resolve_context_from(job)
        assert result == ""

    @pytest.mark.asyncio
    async def test_ref_job_deleted_shows_id_as_fallback(self) -> None:
        """If referenced job is deleted, use job ID as task name."""
        executor, store, _delivery = make_executor()
        run = MagicMock()
        run.output = "some data"
        store.list_runs = AsyncMock(return_value=[run])
        store.get_job = AsyncMock(return_value=None)

        job = make_job(context_from=("deleted-ref",))
        result = await executor._resolve_context_from(job)
        assert "deleted-ref" in result
        assert "some data" in result

    @pytest.mark.asyncio
    async def test_output_truncation(self) -> None:
        """Output exceeding _MAX_CONTEXT_FROM_CHARS is truncated."""
        from myrm_agent_harness.toolkits.cron.engine.executor import _MAX_CONTEXT_FROM_CHARS

        executor, store, _delivery = make_executor()
        long_output = "x" * (_MAX_CONTEXT_FROM_CHARS + 500)
        run = MagicMock()
        run.output = long_output
        ref_job = make_job(id="ref-long", name="Long Output Task")
        store.list_runs = AsyncMock(return_value=[run])
        store.get_job = AsyncMock(return_value=ref_job)

        job = make_job(context_from=("ref-long",))
        result = await executor._resolve_context_from(job)
        assert "[... output truncated ...]" in result
        assert len(result) < len(long_output)

    @pytest.mark.asyncio
    async def test_multiple_refs_joined_with_separator(self) -> None:
        """Multiple refs are joined with --- separator."""
        executor, store, _delivery = make_executor()
        run_a = MagicMock()
        run_a.output = "Data from A"
        run_b = MagicMock()
        run_b.output = "Data from B"

        async def mock_list_runs(job_id: str, **kwargs: object) -> list[MagicMock]:
            return [{"ref-a": run_a, "ref-b": run_b}[job_id]]

        async def mock_get_job(job_id: str) -> CronJob:
            names = {"ref-a": "Task A", "ref-b": "Task B"}
            return make_job(id=job_id, name=names[job_id])

        store.list_runs = AsyncMock(side_effect=mock_list_runs)
        store.get_job = AsyncMock(side_effect=mock_get_job)

        job = make_job(context_from=("ref-a", "ref-b"))
        result = await executor._resolve_context_from(job)
        assert "Task A" in result
        assert "Task B" in result
        assert "---" in result
        assert "Data from A" in result
        assert "Data from B" in result

    @pytest.mark.asyncio
    async def test_context_from_injected_into_runner(self) -> None:
        """Verify context_from text is passed to runner.run() as context."""
        executor, store, _delivery = make_executor()
        run = MagicMock()
        run.output = "injected data"
        ref_job = make_job(id="ref-1", name="Injector")

        store.list_runs = AsyncMock(return_value=[run])
        store.get_job = AsyncMock(return_value=ref_job)

        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=True, output="done"))

        job = make_job(context_from=("ref-1",))
        await executor.run_and_record(job, runner)

        call_kwargs = runner.run.call_args
        context_arg = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context", "")
        assert "injected data" in context_arg
