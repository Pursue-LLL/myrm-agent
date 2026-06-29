"""Tests for heartbeat follow-up delivery finalization in AgentJobRunner."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.heartbeat import HEARTBEAT_JOB_NAME
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobResult,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.agent_runner import (
    _finalize_heartbeat_follow_up_delivery,
    _heartbeat_follow_up_delivered,
)

_CONFIRM_MODULE = "app.core.memory.proactive.delivery_tracker.confirm_follow_up_delivery"
_RESET_MODULE = "app.core.memory.proactive.delivery_tracker.reset_follow_up_delivery"


def _make_heartbeat_job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "hb-1",
        "user_id": "user-1",
        "name": HEARTBEAT_JOB_NAME,
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="*/30 * * * *"),
        "status": JobStatus.ACTIVE,
        "prompt": "Check system status and report any anomalies.",
        "delivery": DeliveryConfig(channel="chat"),
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


def _make_regular_job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "cron-1",
        "user_id": "user-1",
        "name": "Daily Report",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"),
        "status": JobStatus.ACTIVE,
        "prompt": "Generate daily report.",
        "delivery": DeliveryConfig(channel="chat"),
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


class TestHeartbeatFollowUpDelivered:
    """Unit tests for silent-vs-delivered output classification."""

    def test_normal_output_is_delivered(self) -> None:
        assert _heartbeat_follow_up_delivered("Reminder: your interview is tomorrow.") is True

    def test_silent_token_is_not_delivered(self) -> None:
        assert _heartbeat_follow_up_delivered("[SILENT]") is False

    def test_silent_with_whitespace_is_not_delivered(self) -> None:
        assert _heartbeat_follow_up_delivered("  [SILENT]  ") is False

    def test_empty_output_is_not_delivered(self) -> None:
        assert _heartbeat_follow_up_delivered("") is False
        assert _heartbeat_follow_up_delivered(None) is False


class TestFinalizeHeartbeatFollowUpDelivery:
    """Integration tests for post-heartbeat delivery tracker wiring."""

    @pytest.mark.asyncio
    async def test_silent_output_snoozes_via_confirm_false(self) -> None:
        job = _make_heartbeat_job()
        result = JobResult(success=True, output="[SILENT]")

        with patch(_CONFIRM_MODULE, new_callable=AsyncMock) as confirm, patch(_RESET_MODULE) as reset:
            await finalize_heartbeat_follow_up_delivery(job, result)

        confirm.assert_awaited_once_with(delivered=False)
        reset.assert_not_called()

    @pytest.mark.asyncio
    async def test_visible_output_marks_delivered(self) -> None:
        job = _make_heartbeat_job()
        result = JobResult(success=True, output="How did the interview go?")

        with patch(_CONFIRM_MODULE, new_callable=AsyncMock) as confirm, patch(_RESET_MODULE) as reset:
            await finalize_heartbeat_follow_up_delivery(job, result)

        confirm.assert_awaited_once_with(delivered=True)
        reset.assert_not_called()

    @pytest.mark.asyncio
    async def test_skipped_heartbeat_resets_without_confirm(self) -> None:
        job = _make_heartbeat_job()
        result = JobResult(success=True, skipped=True, skip_reason="no-content")

        with patch(_CONFIRM_MODULE, new_callable=AsyncMock) as confirm, patch(_RESET_MODULE) as reset:
            await finalize_heartbeat_follow_up_delivery(job, result)

        confirm.assert_not_awaited()
        reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_heartbeat_resets_without_confirm(self) -> None:
        job = _make_heartbeat_job()
        result = JobResult(success=False, error="agent failed")

        with patch(_CONFIRM_MODULE, new_callable=AsyncMock) as confirm, patch(_RESET_MODULE) as reset:
            await finalize_heartbeat_follow_up_delivery(job, result)

        confirm.assert_not_awaited()
        reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_heartbeat_job_is_noop(self) -> None:
        job = _make_regular_job()
        result = JobResult(success=True, output="[SILENT]")

        with patch(_CONFIRM_MODULE, new_callable=AsyncMock) as confirm, patch(_RESET_MODULE) as reset:
            await finalize_heartbeat_follow_up_delivery(job, result)

        confirm.assert_not_awaited()
        reset.assert_not_called()
