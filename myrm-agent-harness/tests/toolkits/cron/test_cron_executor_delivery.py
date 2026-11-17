"""Unit tests for JobExecutor output hashing, delivery and failure alerting."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.engine.executor import _output_hash
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    DeliveryConfig,
    DeliveryStatus,
    FailureAlertConfig,
    JobResult,
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
