"""Unit tests for JobExecutor's run-and-record path, runner skips and runner deferrals."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryStatus,
    JobResult,
    JobStatus,
    RunStatus,
    ScheduleKind,
)
from tests.support.cron_executor_mocks import make_executor, make_job, make_schedule, store_holds

# ---------------------------------------------------------------------------
# run_and_record — full lifecycle
# ---------------------------------------------------------------------------


class TestRunAndRecord:
    @pytest.mark.asyncio
    async def test_success_flow(self) -> None:
        executor, store, _delivery = make_executor()
        job = make_job()
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=True, output="result"))
        await executor.run_and_record(job, runner)
        runner.run.assert_awaited_once_with(job, context="")
        store.save_run.assert_awaited_once()
        store.save_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_timeout_flow(self) -> None:
        executor, store, _delivery = make_executor()
        job = make_job(timeout_seconds=10)
        runner = AsyncMock()

        async def slow_run(_: CronJob, **_kw: object) -> JobResult:
            await asyncio.sleep(100)
            return JobResult(success=True, output="never")

        runner.run = slow_run

        async def timeout_and_close(*args: object, **_kwargs: object) -> object:
            coro = args[0] if args else None
            if coro is not None and hasattr(coro, "close"):
                coro.close()
            raise TimeoutError

        with patch("asyncio.wait_for", side_effect=timeout_and_close):
            await executor.run_and_record(job, runner)
        saved_run = store.save_run.call_args[0][0]
        assert saved_run.status == RunStatus.ERROR
        assert "timed out" in (saved_run.error or "")

    @pytest.mark.asyncio
    async def test_monitor_no_new_content_skips_delivery(self) -> None:
        """When monitor detects no change, exit_code=0 → delivery skipped."""
        executor, _store, delivery = make_executor()
        from myrm_agent_harness.infra.incremental.types import MonitorConfig

        mc = MonitorConfig(enabled=True, monitor_type="hash")
        job = make_job(monitor_config=mc)
        result = JobResult(success=True, output="same content", exit_code=0)

        runner = AsyncMock()
        runner.run = AsyncMock(return_value=result)

        with patch.object(executor._monitor_manager, "get_monitor") as mock_get:
            mock_monitor = MagicMock()
            mock_monitor.is_baseline.return_value = False
            mock_monitor.compute_delta.return_value = ""
            mock_get.return_value = (mock_monitor, None)

            with patch.object(executor._monitor_manager, "save_monitor_state", new_callable=AsyncMock):
                await executor.run_and_record(job, runner)

        delivery.deliver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_json_like_monitor_output_emits_visible_warning(self) -> None:
        """Invalid JSON-like monitor output should not silently disappear."""
        executor, store, delivery = make_executor()
        from myrm_agent_harness.infra.incremental.hash_monitor import (
            InvalidJsonLikeMonitorOutputError,
        )
        from myrm_agent_harness.infra.incremental.types import MonitorConfig

        mc = MonitorConfig(enabled=True, monitor_type="hash")
        job = make_job(monitor_config=mc)
        result = JobResult(success=True, output='{"asset":"BTC"')

        runner = AsyncMock()
        runner.run = AsyncMock(return_value=result)

        with patch.object(executor._monitor_manager, "get_monitor") as mock_get:
            mock_monitor = MagicMock()
            mock_monitor.is_baseline.return_value = False
            mock_monitor.compute_delta.side_effect = InvalidJsonLikeMonitorOutputError(
                "invalid JSON-like monitor output"
            )
            mock_get.return_value = (mock_monitor, None)

            with patch.object(
                executor._monitor_manager, "record_monitor_failure", new_callable=AsyncMock
            ) as mock_record:
                mock_record.return_value = 1
                await executor.run_and_record(job, runner)

        delivery.deliver.assert_awaited_once()
        saved_run = store.save_run.call_args[0][0]
        assert saved_run.status == RunStatus.ERROR
        assert saved_run.output is not None
        assert "Monitoring output format is invalid" in saved_run.output
        assert saved_run.error is not None
        assert "Monitoring output format is invalid" in saved_run.error
        assert saved_run.metadata is not None
        assert saved_run.metadata.get("monitor_contract_error") == "invalid_json_like_output"
        saved_job = store.save_job.call_args[0][0]
        assert saved_job.consecutive_failures == 1
        assert saved_job.last_status == RunStatus.ERROR

    @pytest.mark.asyncio
    async def test_repeated_invalid_json_contract_error_dedups_main_delivery(self) -> None:
        """Repeated contract errors should not spam the main delivery channel."""
        executor, store, delivery = make_executor()
        from myrm_agent_harness.infra.incremental.hash_monitor import (
            InvalidJsonLikeMonitorOutputError,
        )
        from myrm_agent_harness.infra.incremental.types import MonitorConfig

        mc = MonitorConfig(enabled=True, monitor_type="hash")
        job = make_job(monitor_config=mc)
        result = JobResult(success=True, output='{"asset":"BTC"')

        runner = AsyncMock()
        runner.run = AsyncMock(return_value=result)

        with patch.object(executor._monitor_manager, "get_monitor") as mock_get:
            mock_monitor = MagicMock()
            mock_monitor.is_baseline.return_value = False
            mock_monitor.compute_delta.side_effect = InvalidJsonLikeMonitorOutputError(
                "invalid JSON-like monitor output"
            )
            mock_get.return_value = (mock_monitor, None)

            with patch.object(
                executor._monitor_manager, "record_monitor_failure", new_callable=AsyncMock
            ) as mock_record:
                mock_record.return_value = 2
                await executor.run_and_record(job, runner)

        delivery.deliver.assert_not_awaited()
        saved_run = store.save_run.call_args[0][0]
        assert saved_run.status == RunStatus.ERROR
        assert saved_run.delivery_status == DeliveryStatus.SKIPPED
        assert saved_run.delivery_error == "monitor_contract_error_dedup"
        assert saved_run.metadata is not None
        assert saved_run.metadata.get("monitor_failure_count") == 2

    @pytest.mark.asyncio
    async def test_contract_error_uses_memory_fallback_count_when_store_unavailable(self) -> None:
        """Contract-error dedup should still work when monitor-state persistence fails."""
        executor, store, delivery = make_executor()
        from myrm_agent_harness.infra.incremental.hash_monitor import (
            InvalidJsonLikeMonitorOutputError,
        )
        from myrm_agent_harness.infra.incremental.types import MonitorConfig

        mc = MonitorConfig(enabled=True, monitor_type="hash")
        job = make_job(monitor_config=mc)
        store_holds(store, job)
        result = JobResult(success=True, output='{"asset":"BTC"')
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=result)

        with patch.object(executor._monitor_manager, "get_monitor") as mock_get:
            mock_monitor = MagicMock()
            mock_monitor.is_baseline.return_value = False
            mock_monitor.compute_delta.side_effect = InvalidJsonLikeMonitorOutputError(
                "invalid JSON-like monitor output"
            )
            mock_get.return_value = (mock_monitor, None)

            with patch.object(
                executor._monitor_manager, "record_monitor_failure", new_callable=AsyncMock
            ) as mock_record:
                mock_record.side_effect = RuntimeError("monitor state store unavailable")
                await executor.run_and_record(job, runner)
                await executor.run_and_record(job, runner)

        assert delivery.deliver.await_count == 1
        first_run = store.save_run.call_args_list[0][0][0]
        second_run = store.save_run.call_args_list[1][0][0]
        assert first_run.metadata is not None
        assert first_run.metadata.get("monitor_failure_count") == 1
        assert first_run.metadata.get("monitor_failure_count_source") == "memory_fallback"
        assert second_run.metadata is not None
        assert second_run.metadata.get("monitor_failure_count") == 2
        assert second_run.delivery_status == DeliveryStatus.SKIPPED
        assert second_run.delivery_error == "monitor_contract_error_dedup"


# ---------------------------------------------------------------------------
# Runner-level skip (JobResult.skipped)
# ---------------------------------------------------------------------------


class TestRunnerSkip:
    @pytest.mark.asyncio
    async def test_skipped_result_records_skipped_status(self) -> None:
        """Runner returning skipped=True should record SKIPPED, skip delivery."""
        executor, store, delivery = make_executor()
        job = make_job()
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=True, skipped=True, skip_reason="no-content"))
        await executor.run_and_record(job, runner)

        saved_run = store.save_run.call_args[0][0]
        assert saved_run.status == RunStatus.SKIPPED
        assert saved_run.delivery_status == DeliveryStatus.SKIPPED
        assert saved_run.output == "no-content"
        delivery.deliver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skipped_without_reason(self) -> None:
        """Skipped result with no reason should still record SKIPPED."""
        executor, store, _delivery = make_executor()
        job = make_job()
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=True, skipped=True))
        await executor.run_and_record(job, runner)

        saved_run = store.save_run.call_args[0][0]
        assert saved_run.status == RunStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_skipped_advances_schedule(self) -> None:
        """Skipped job should advance next_run_at for recurring schedule."""
        executor, store, _ = make_executor()
        job = make_job()
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=True, skipped=True, skip_reason="no-content"))
        await executor.run_and_record(job, runner)

        assert job.last_status == RunStatus.SKIPPED
        assert job.status == JobStatus.ACTIVE
        store.save_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skipped_once_with_delete(self) -> None:
        """One-shot job with delete_after_run=True skipped by runner should be deleted."""
        executor, store, _ = make_executor()
        job = make_job(
            schedule=make_schedule(ScheduleKind.ONCE),
            delete_after_run=True,
        )
        store_holds(store, job)
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=JobResult(success=True, skipped=True, skip_reason="no-content"))
        await executor.run_and_record(job, runner)

        store.delete_job.assert_awaited_once_with("job-1")


class TestRunnerDeferral:
    """``JobResult.retry_at``: the run cannot succeed before that instant."""

    @staticmethod
    def _deferred(reason: str = "usage-limit", *, skipped: bool = False) -> tuple[JobResult, datetime]:
        retry_at = datetime.now(UTC) + timedelta(hours=3)
        return JobResult(success=False, error="limit", skip_reason=reason, retry_at=retry_at, skipped=skipped), retry_at

    @pytest.mark.asyncio
    async def test_rearms_job_without_counting_a_failure(self) -> None:
        executor, store, delivery = make_executor()
        job = make_job(consecutive_failures=2)
        store_holds(store, job)
        result, retry_at = self._deferred()
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=result)

        await executor.run_and_record(job, runner)

        saved_run = store.save_run.call_args[0][0]
        assert saved_run.status == RunStatus.SKIPPED
        assert saved_run.output == "usage-limit"
        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at == retry_at
        assert job.last_status == RunStatus.SKIPPED
        assert job.consecutive_failures == 2
        assert job.last_failure_alert_at is None
        delivery.deliver.assert_not_awaited()
        store.save_job.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("delete_after_run", [False, True])
    async def test_one_shot_job_stays_alive(self, delete_after_run: bool) -> None:
        executor, store, _ = make_executor()
        job = make_job(schedule=make_schedule(ScheduleKind.ONCE), delete_after_run=delete_after_run)
        result, retry_at = self._deferred()
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=result)

        await executor.run_and_record(job, runner)

        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at == retry_at
        store.delete_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_takes_precedence_over_skipped_for_one_shot_jobs(self) -> None:
        """A load-shed one-shot run is retried, not consumed like a no-content skip."""
        executor, store, _ = make_executor()
        job = make_job(schedule=make_schedule(ScheduleKind.ONCE), delete_after_run=True)
        result, retry_at = self._deferred("memory_pressure:high", skipped=True)
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=result)

        await executor.run_and_record(job, runner)

        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at == retry_at
        store.delete_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_job_deleted_during_run_is_neither_recorded_nor_resurrected(self) -> None:
        executor, store, _ = make_executor()
        store.get_job = AsyncMock(return_value=None)
        job = make_job()
        result, _ = self._deferred()
        runner = AsyncMock()
        runner.run = AsyncMock(return_value=result)

        await executor.run_and_record(job, runner)

        store.save_run.assert_not_awaited()
        store.save_job.assert_not_awaited()
