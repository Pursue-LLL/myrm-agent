"""Unit tests for the TracingContext JobExecutor sets around a run, and the run outcomes recorded alongside it."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.observability.tracing import TracingContext
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronRunRecord,
    DeliveryConfig,
    DeliveryStatus,
    JobResult,
    JobStatus,
    RunStatus,
)
from tests.support.cron_executor_mocks import make_executor, make_job


def _record_saved_runs(store: AsyncMock) -> list[CronRunRecord]:
    """Make the mocked store keep every run it is asked to save and hand the record back, as a real store does."""
    saved_runs: list[CronRunRecord] = []

    def save_run(record: CronRunRecord) -> CronRunRecord:
        saved_runs.append(record)
        return record

    store.save_run = AsyncMock(side_effect=save_run)
    return saved_runs


# ---------------------------------------------------------------------------
# TracingContext injection in run_and_record
# ---------------------------------------------------------------------------


class TestRunAndRecordTracing:
    """Verify TracingContext is properly set during execution and reset after."""

    @pytest.mark.asyncio
    async def test_trace_id_set_during_execution(self) -> None:
        """trace_id should be a valid 32-char hex during runner.run()."""
        executor, _store, _delivery = make_executor()
        job = make_job()
        captured_trace_id: str = ""

        async def capturing_run(_job: CronJob, **_kw: object) -> JobResult:
            nonlocal captured_trace_id
            captured_trace_id = TracingContext.get_trace_id()
            return JobResult(success=True, output="ok")

        runner = AsyncMock()
        runner.run = capturing_run

        await executor.run_and_record(job, runner)

        assert captured_trace_id != "-"
        assert len(captured_trace_id) == 32
        int(captured_trace_id, 16)  # valid hex

    @pytest.mark.asyncio
    async def test_session_id_set_to_job_id(self) -> None:
        """session_id should equal job.id during execution."""
        executor, _store, _delivery = make_executor()
        job = make_job(id="my-cron-job-42")
        captured_session_id: str = ""

        async def capturing_run(_job: CronJob, **_kw: object) -> JobResult:
            nonlocal captured_session_id
            captured_session_id = TracingContext.get_session_id()
            return JobResult(success=True, output="ok")

        runner = AsyncMock()
        runner.run = capturing_run

        await executor.run_and_record(job, runner)

        assert captured_session_id == "my-cron-job-42"

    @pytest.mark.asyncio
    async def test_context_reset_after_success(self) -> None:
        """TracingContext must be reset to defaults after run_and_record completes."""
        executor, _store, _delivery = make_executor()
        job = make_job()
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=True, output="ok"))

        await executor.run_and_record(job, runner)

        assert TracingContext.get_trace_id() == "-"
        assert TracingContext.get_session_id() == "-"

    @pytest.mark.asyncio
    async def test_context_reset_after_runner_exception(self) -> None:
        """TracingContext must be reset even when runner raises an exception."""
        executor, _store, _delivery = make_executor()
        job = make_job()
        runner = AsyncMock()
        runner.run = AsyncMock(side_effect=RuntimeError("unexpected crash"))

        with pytest.raises(RuntimeError, match="unexpected crash"):
            await executor.run_and_record(job, runner)

        assert TracingContext.get_trace_id() == "-"
        assert TracingContext.get_session_id() == "-"

    @pytest.mark.asyncio
    async def test_each_execution_gets_unique_trace_id(self) -> None:
        """Consecutive calls to run_and_record produce distinct trace_ids."""
        executor, _store, _delivery = make_executor()
        captured_ids: list[str] = []

        async def capturing_run(_job: CronJob, **_kw: object) -> JobResult:
            captured_ids.append(TracingContext.get_trace_id())
            return JobResult(success=True, output="ok")

        runner = AsyncMock()
        runner.run = capturing_run
        job = make_job()

        await executor.run_and_record(job, runner)
        await executor.run_and_record(job, runner)

        assert len(captured_ids) == 2
        assert captured_ids[0] != captured_ids[1]

    @pytest.mark.asyncio
    async def test_context_reset_after_timeout(self) -> None:
        """TracingContext resets after job timeout (TimeoutError path)."""
        executor, _store, _delivery = make_executor()
        job = make_job(timeout_seconds=10)

        async def slow_run(_job: CronJob, **_kw: object) -> JobResult:
            await asyncio.sleep(100)
            return JobResult(success=True, output="never")

        runner = AsyncMock()
        runner.run = slow_run

        async def timeout_and_close(*args: object, **_kwargs: object) -> object:
            coro = args[0] if args else None
            if coro is not None and hasattr(coro, "close"):
                coro.close()
            raise TimeoutError

        with patch("asyncio.wait_for", side_effect=timeout_and_close):
            await executor.run_and_record(job, runner)

        assert TracingContext.get_trace_id() == "-"
        assert TracingContext.get_session_id() == "-"

    @pytest.mark.asyncio
    async def test_trace_active_during_skipped_runner(self) -> None:
        """trace_id is set during runner execution even when result is skipped."""
        executor, _store, _delivery = make_executor()
        job = make_job()
        captured_trace_id: str = ""

        async def skip_run(_job: CronJob, **_kw: object) -> JobResult:
            nonlocal captured_trace_id
            captured_trace_id = TracingContext.get_trace_id()
            return JobResult(success=True, skipped=True, skip_reason="no-content")

        runner = AsyncMock()
        runner.run = skip_run

        await executor.run_and_record(job, runner)

        assert captured_trace_id != "-"
        assert len(captured_trace_id) == 32
        assert TracingContext.get_trace_id() == "-"

    @pytest.mark.asyncio
    async def test_context_reset_after_store_exception(self) -> None:
        """TracingContext resets even when store.save_run raises."""
        executor, store, _delivery = make_executor()
        store.save_run = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        job = make_job()
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=True, output="ok"))

        with pytest.raises(RuntimeError, match="DB connection lost"):
            await executor.run_and_record(job, runner)

        assert TracingContext.get_trace_id() == "-"
        assert TracingContext.get_session_id() == "-"

    @pytest.mark.asyncio
    async def test_delivery_failure_records_connector_failure_in_run_metadata(self) -> None:
        """A failed delivery puts the classified, credential-free connector failure into the run's metadata."""
        executor, store, delivery = make_executor()
        job = make_job(
            delivery=DeliveryConfig(channel="webhook", target="https://api.example.com/webhook?token=secret99"),
            consecutive_failures=2,
        )
        delivery.deliver = AsyncMock(side_effect=RuntimeError("Webhook returned 502: Bad Gateway"))

        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=False, error="Webhook returned 502: Bad Gateway"))

        saved_runs = _record_saved_runs(store)

        await executor.run_and_record(job, runner)

        assert len(saved_runs) == 1
        run_record = saved_runs[0]
        assert run_record.delivery_status == DeliveryStatus.FAILED
        assert run_record.metadata is not None
        assert "connector_failure" in run_record.metadata
        conn_fail = run_record.metadata["connector_failure"]
        assert isinstance(conn_fail, dict)
        assert set(conn_fail) == {"category", "target"}
        assert conn_fail["category"] == "http_server_error"
        assert "secret99" not in conn_fail["target"]
        assert run_record.delivery_error is not None
        assert "502" in run_record.delivery_error

        assert job.consecutive_failures == 3

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("runner_metadata", "expected_category"),
        [
            ({"verification": {"status": "passed"}}, "http_server_error"),
            ({"connector_failure": {"category": "reported_by_runner"}}, "reported_by_runner"),
        ],
    )
    async def test_delivery_failure_joins_run_metadata_without_overwriting_it(
        self, runner_metadata: dict[str, object], expected_category: str
    ) -> None:
        executor, store, delivery = make_executor()
        job = make_job(delivery=DeliveryConfig(channel="webhook", target="https://api.example.com/webhook"))
        delivery.deliver = AsyncMock(side_effect=RuntimeError("Webhook returned 502: Bad Gateway"))
        original = deepcopy(runner_metadata)
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=True, output="ok", metadata=runner_metadata))
        saved_runs = _record_saved_runs(store)

        await executor.run_and_record(job, runner)

        metadata = saved_runs[0].metadata
        assert metadata is not None
        conn_fail = metadata["connector_failure"]
        assert isinstance(conn_fail, dict)
        assert conn_fail["category"] == expected_category
        assert {key: metadata[key] for key in runner_metadata if key != "connector_failure"} == {
            key: value for key, value in original.items() if key != "connector_failure"
        }
        assert runner_metadata == original

    @pytest.mark.asyncio
    async def test_circuit_break_pauses_job_and_marks_run_status(self) -> None:
        """When JobResult is circuit_broken, run status is CIRCUIT_BREAK and job is auto-paused."""
        executor, store, _delivery = make_executor()
        job = make_job()
        runner = AsyncMock()
        runner.run = AsyncMock(
            return_value=JobResult(
                success=False,
                error="RUNAWAY_CIRCUIT_BREAKER: 3 identical failures",
                circuit_broken=True,
            )
        )

        saved_runs = _record_saved_runs(store)

        await executor.run_and_record(job, runner)

        assert len(saved_runs) == 1
        assert saved_runs[0].status == RunStatus.CIRCUIT_BREAK
        assert job.status == JobStatus.PAUSED
        assert job.next_run_at is None
        assert job.last_status == RunStatus.CIRCUIT_BREAK
