"""Unit tests for JobExecutor output hashing, delivery and failure alerting."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from myrm_agent_harness.toolkits.cron.engine.connector_health import delivery_target_key
from myrm_agent_harness.toolkits.cron.engine.executor import _output_hash
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    CronJob,
    CronRunRecord,
    DeliveryConfig,
    DeliveryStatus,
    FailureAlertConfig,
    JobResult,
    JobStatus,
)
from tests.support.cron_executor_mocks import make_executor, make_job

# ---------------------------------------------------------------------------
# _output_hash
# ---------------------------------------------------------------------------


class TestOutputHash:
    def test_deterministic(self) -> None:
        h1 = _output_hash("hello world")
        h2 = _output_hash("hello world")
        assert h1 == h2
        assert len(h1) == 32

    def test_strips_whitespace(self) -> None:
        assert _output_hash("  hello  ") == _output_hash("hello")


# ---------------------------------------------------------------------------
# _try_deliver
# ---------------------------------------------------------------------------


class TestTryDeliver:
    @pytest.mark.asyncio
    async def test_skip_none_channel(self) -> None:
        executor, _, _ = make_executor()
        job = make_job(delivery=DeliveryConfig(channel="none"))
        result = JobResult(success=True, output="hi")
        status, error = await executor._try_deliver(job, result)
        assert status == DeliveryStatus.SKIPPED
        assert error is None

    @pytest.mark.asyncio
    async def test_silent_response_skipped(self) -> None:
        executor, _, _ = make_executor()
        job = make_job()
        result = JobResult(success=True, output="[SILENT]")
        status, error = await executor._try_deliver(job, result)
        assert status == DeliveryStatus.SKIPPED
        assert error == "silent_response"

    @pytest.mark.asyncio
    async def test_empty_success_output_skipped(self) -> None:
        executor, _, delivery = make_executor()
        job = make_job()
        result = JobResult(success=True, output="   ")
        status, error = await executor._try_deliver(job, result)
        assert status == DeliveryStatus.SKIPPED
        assert error == "empty_output"
        delivery.deliver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_silent_with_suffix_delivers(self) -> None:
        executor, _, delivery = make_executor()
        job = make_job()
        result = JobResult(success=True, output="[SILENT] nothing to report")
        status, error = await executor._try_deliver(job, result)
        assert status == DeliveryStatus.DELIVERED
        assert error is None
        delivery.deliver.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delivery_success(self) -> None:
        executor, _, delivery = make_executor()
        job = make_job()
        result = JobResult(success=True, output="some output")
        status, error = await executor._try_deliver(job, result)
        assert status == DeliveryStatus.DELIVERED
        assert error is None
        delivery.deliver.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delivery_failure(self) -> None:
        executor, _, delivery = make_executor()
        delivery.deliver = AsyncMock(side_effect=RuntimeError("network error"))
        job = make_job()
        result = JobResult(success=True, output="some output")
        status, error = await executor._try_deliver(job, result)
        assert status == DeliveryStatus.FAILED
        assert "network error" in (error or "")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("failure", "named"),
        [(TimeoutError(), "TimeoutError"), (httpx.ReadTimeout(""), "ReadTimeout")],
        ids=["TimeoutError", "ReadTimeout"],
    )
    async def test_a_failure_without_text_is_recorded_by_its_type(self, failure: Exception, named: str) -> None:
        executor, _, delivery = make_executor()
        delivery.deliver = AsyncMock(side_effect=failure)
        status, error = await executor._try_deliver(make_job(), JobResult(success=True, output="some output"))
        assert status == DeliveryStatus.FAILED
        assert error == named

    @pytest.mark.asyncio
    async def test_duplicate_output_skipped(self) -> None:
        executor, _, _ = make_executor()
        job = make_job(deduplicate=True, last_output_hash=_output_hash("same output"))
        result = JobResult(success=True, output="same output")
        status, error = await executor._try_deliver(job, result)
        assert status == DeliveryStatus.SKIPPED
        assert error == "duplicate_output"

    @pytest.mark.asyncio
    async def test_incremental_delta_delivered(self) -> None:
        executor, _, delivery = make_executor()
        job = make_job()
        result = JobResult(
            success=True,
            output="full output here",
            incremental_delta="only the new part",
        )
        status, _ = await executor._try_deliver(job, result)
        assert status == DeliveryStatus.DELIVERED
        delivered_result = delivery.deliver.call_args[0][1]
        assert delivered_result.output == "only the new part"

    @pytest.mark.asyncio
    async def test_dedup_hash_updated_after_delivery(self) -> None:
        executor, _, _ = make_executor()
        job = make_job(deduplicate=True, last_output_hash=None)
        result = JobResult(success=True, output="new output")
        await executor._try_deliver(job, result)
        assert job.last_output_hash == _output_hash("new output")


# ---------------------------------------------------------------------------
# The destination key a run record carries
# ---------------------------------------------------------------------------

WEBHOOK = DeliveryConfig(channel="webhook", target="https://api.example.com/hook?token=secret99")


async def _record_run(job: CronJob, *, result: JobResult, delivery_error: Exception | None = None) -> CronRunRecord:
    """Run the job once through a fresh executor and hand back the record it saved."""
    executor, store, delivery = make_executor()
    if delivery_error is not None:
        delivery.deliver = AsyncMock(side_effect=delivery_error)
    runner = AsyncMock()
    runner.run = AsyncMock(return_value=result)
    await executor.run_and_record(job, runner)
    store.save_run.assert_awaited_once()
    record: CronRunRecord = store.save_run.await_args.args[0]
    return record


class TestRunDeliveryKey:
    @pytest.mark.asyncio
    async def test_a_delivered_run_carries_the_key_of_its_destination(self) -> None:
        record = await _record_run(make_job(delivery=WEBHOOK), result=JobResult(success=True, output="report"))
        assert record.delivery_status == DeliveryStatus.DELIVERED
        assert record.metadata is not None
        assert record.metadata["delivery_key"] == delivery_target_key("webhook", WEBHOOK.target)
        assert "secret99" not in str(record.metadata)

    @pytest.mark.asyncio
    async def test_a_failed_delivery_carries_the_same_key(self) -> None:
        record = await _record_run(
            make_job(delivery=WEBHOOK),
            result=JobResult(success=True, output="report"),
            delivery_error=RuntimeError("Webhook returned 502: Bad Gateway"),
        )
        assert record.delivery_status == DeliveryStatus.FAILED
        assert record.metadata is not None
        assert record.metadata["delivery_key"] == delivery_target_key("webhook", WEBHOOK.target)
        assert "connector_failure" in record.metadata

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("delivery", "output"),
        [
            (DeliveryConfig(channel="chat"), "report"),
            (DeliveryConfig(channel="none"), "report"),
            (WEBHOOK, "[SILENT]"),
        ],
        ids=["in-app-channel", "no-delivery", "skipped-delivery"],
    )
    async def test_a_run_that_reached_no_destination_carries_no_key(
        self, delivery: DeliveryConfig, output: str
    ) -> None:
        record = await _record_run(make_job(delivery=delivery), result=JobResult(success=True, output=output))
        assert "delivery_key" not in (record.metadata or {})

    @pytest.mark.asyncio
    async def test_the_runner_cannot_name_the_destination(self) -> None:
        record = await _record_run(
            make_job(delivery=WEBHOOK),
            result=JobResult(success=True, output="report", metadata={"delivery_key": "forged"}),
        )
        assert record.metadata is not None
        assert record.metadata["delivery_key"] == delivery_target_key("webhook", WEBHOOK.target)


# ---------------------------------------------------------------------------
# _maybe_send_failure_alert
# ---------------------------------------------------------------------------


class TestMaybeSendFailureAlert:
    def test_no_alert_config(self) -> None:
        executor, _, _delivery = make_executor()
        job = make_job(failure_alert=None)
        now = datetime.now(UTC)
        executor._maybe_send_failure_alert(job, 3, now)
        assert job.last_failure_alert_at is None

    @pytest.mark.asyncio
    async def test_alert_sent(self) -> None:
        executor, _, _delivery = make_executor(config=CronConfig(failure_alert=FailureAlertConfig(after=2)))
        job = make_job(failure_alert=None, consecutive_failures=3)
        now = datetime.now(UTC)
        executor._maybe_send_failure_alert(job, 3, now)
        assert job.last_failure_alert_at == now

    @pytest.mark.asyncio
    async def test_alert_with_custom_delivery(self) -> None:
        custom = DeliveryConfig(channel="webhook", target="https://alert.example.com")
        executor, _, _delivery = make_executor(
            config=CronConfig(failure_alert=FailureAlertConfig(after=1, delivery=custom))
        )
        job = make_job(failure_alert=None, consecutive_failures=3)
        now = datetime.now(UTC)
        executor._maybe_send_failure_alert(job, 3, now)
        assert job.last_failure_alert_at == now

    @pytest.mark.asyncio
    async def test_an_active_job_below_the_threshold_is_not_alerted(self) -> None:
        executor, _, delivery = make_executor(config=CronConfig(failure_alert=FailureAlertConfig(after=3)))
        job = make_job(failure_alert=None, consecutive_failures=1)
        executor._maybe_send_failure_alert(job, 1, datetime.now(UTC))
        await asyncio.sleep(0)
        assert job.last_failure_alert_at is None
        delivery.deliver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_job_the_failure_paused_is_alerted_below_the_threshold(self) -> None:
        executor, _, delivery = make_executor(config=CronConfig(failure_alert=FailureAlertConfig(after=3)))
        job = make_job(failure_alert=None, consecutive_failures=1, status=JobStatus.PAUSED, last_error="loop")
        now = datetime.now(UTC)
        executor._maybe_send_failure_alert(job, 1, now)
        await asyncio.sleep(0)
        assert job.last_failure_alert_at == now
        delivery.deliver.assert_awaited_once()
        assert "auto-paused" in delivery.deliver.call_args[0][1].output

    @pytest.mark.asyncio
    async def test_a_job_the_failure_paused_is_alerted_inside_the_cooldown_of_an_earlier_alert(self) -> None:
        executor, _, delivery = make_executor(
            config=CronConfig(failure_alert=FailureAlertConfig(after=1, cooldown_seconds=3600))
        )
        now = datetime.now(UTC)
        earlier = now - timedelta(seconds=30)
        active = make_job(failure_alert=None, consecutive_failures=2, last_failure_alert_at=earlier)
        executor._maybe_send_failure_alert(active, 2, now)
        await asyncio.sleep(0)
        assert active.last_failure_alert_at == earlier
        delivery.deliver.assert_not_awaited()

        paused = make_job(
            failure_alert=None, consecutive_failures=3, status=JobStatus.PAUSED, last_failure_alert_at=earlier
        )
        executor._maybe_send_failure_alert(paused, 3, now)
        await asyncio.sleep(0)
        assert paused.last_failure_alert_at == now
        delivery.deliver.assert_awaited_once()
