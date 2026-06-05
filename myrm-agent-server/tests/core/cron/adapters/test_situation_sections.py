"""Unit tests for situation section implementations.

Validates SystemHealthSection and PendingRemindersSection behavior
including the no-content (None) return path that enables heartbeat skip.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.situation import SituationContext
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.situation_sections import (
    PendingRemindersSection,
    SystemHealthSection,
)

_CRON_STORE_PATH = "app.core.cron.adapters.setup.get_cron_store"


def _ctx(user_id: str = "user-1") -> SituationContext:
    return SituationContext(
        last_tick_at=datetime.now(UTC) - timedelta(minutes=30),
        agent_id="agent-1",
        user_id=user_id,
    )


def _make_job(
    name: str = "test-job",
    status: JobStatus = JobStatus.ACTIVE,
    consecutive_failures: int = 0,
    schedule_kind: ScheduleKind = ScheduleKind.CRON,
    next_run_at: datetime | None = None,
) -> CronJob:
    return CronJob(
        id=f"job-{name}",
        user_id="user-1",
        name=name,
        job_type=JobType.AGENT,
        schedule=Schedule(
            kind=schedule_kind,
            expr="0 * * * *" if schedule_kind == ScheduleKind.CRON else None,
            run_at=next_run_at if schedule_kind == ScheduleKind.ONCE else None,
        ),
        status=status,
        prompt="test",
        delivery=DeliveryConfig(channel="chat"),
        consecutive_failures=consecutive_failures,
        next_run_at=next_run_at,
    )


class TestSystemHealthSection:
    @pytest.mark.asyncio
    async def test_no_failures_returns_none(self) -> None:
        store = AsyncMock()
        store.list_jobs = AsyncMock(
            return_value=[
                _make_job("job-a", consecutive_failures=0),
                _make_job("job-b", consecutive_failures=1),
            ]
        )
        with patch(_CRON_STORE_PATH, return_value=store):
            section = SystemHealthSection()
            result = await section.build(_ctx())
        assert result is None

    @pytest.mark.asyncio
    async def test_failures_above_threshold_returns_content(self) -> None:
        store = AsyncMock()
        store.list_jobs = AsyncMock(
            return_value=[
                _make_job("healthy-job", consecutive_failures=0),
                _make_job("failing-job", consecutive_failures=5),
            ]
        )
        with patch(_CRON_STORE_PATH, return_value=store):
            section = SystemHealthSection()
            result = await section.build(_ctx())
        assert result is not None
        assert "failing-job" in result
        assert "5 consecutive failures" in result

    @pytest.mark.asyncio
    async def test_paused_jobs_ignored(self) -> None:
        store = AsyncMock()
        store.list_jobs = AsyncMock(
            return_value=[
                _make_job("paused-fail", status=JobStatus.PAUSED, consecutive_failures=10),
            ]
        )
        with patch(_CRON_STORE_PATH, return_value=store):
            section = SystemHealthSection()
            result = await section.build(_ctx())
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_job_list_returns_none(self) -> None:
        store = AsyncMock()
        store.list_jobs = AsyncMock(return_value=[])
        with patch(_CRON_STORE_PATH, return_value=store):
            section = SystemHealthSection()
            result = await section.build(_ctx())
        assert result is None

    @pytest.mark.asyncio
    async def test_threshold_boundary(self) -> None:
        store = AsyncMock()
        store.list_jobs = AsyncMock(
            return_value=[
                _make_job("boundary-2", consecutive_failures=2),
                _make_job("boundary-3", consecutive_failures=3),
            ]
        )
        with patch(_CRON_STORE_PATH, return_value=store):
            section = SystemHealthSection()
            result = await section.build(_ctx())
        assert result is not None
        assert "boundary-3" in result
        assert "boundary-2" not in result


class TestPendingRemindersSection:
    @pytest.mark.asyncio
    async def test_no_active_reminders_returns_none(self) -> None:
        store = AsyncMock()
        store.list_jobs = AsyncMock(
            return_value=[
                _make_job("paused", status=JobStatus.PAUSED),
            ]
        )
        with patch(_CRON_STORE_PATH, return_value=store):
            section = PendingRemindersSection()
            result = await section.build(_ctx())
        assert result is None

    @pytest.mark.asyncio
    async def test_once_job_with_future_trigger(self) -> None:
        store = AsyncMock()
        future = datetime.now(UTC) + timedelta(hours=2)
        store.list_jobs = AsyncMock(
            return_value=[
                _make_job("reminder", schedule_kind=ScheduleKind.ONCE, next_run_at=future),
            ]
        )
        with patch(_CRON_STORE_PATH, return_value=store):
            section = PendingRemindersSection()
            result = await section.build(_ctx())
        assert result is not None
        assert "reminder" in result
        assert "triggers in" in result

    @pytest.mark.asyncio
    async def test_recurring_with_failures(self) -> None:
        store = AsyncMock()
        store.list_jobs = AsyncMock(
            return_value=[
                _make_job("failing-cron", consecutive_failures=2),
            ]
        )
        with patch(_CRON_STORE_PATH, return_value=store):
            section = PendingRemindersSection()
            result = await section.build(_ctx())
        assert result is not None
        assert "2 consecutive failures" in result

    @pytest.mark.asyncio
    async def test_once_job_past_trigger_excluded(self) -> None:
        """ONCE jobs with next_run_at in the past should not appear."""
        store = AsyncMock()
        past = datetime.now(UTC) - timedelta(hours=1)
        store.list_jobs = AsyncMock(
            return_value=[
                _make_job("past-reminder", schedule_kind=ScheduleKind.ONCE, next_run_at=past),
            ]
        )
        with patch(_CRON_STORE_PATH, return_value=store):
            section = PendingRemindersSection()
            result = await section.build(_ctx())
        assert result is None

    @pytest.mark.asyncio
    async def test_internal_jobs_skipped(self) -> None:
        store = AsyncMock()
        store.list_jobs = AsyncMock(
            return_value=[
                _make_job("__heartbeat", consecutive_failures=5),
            ]
        )
        with patch(_CRON_STORE_PATH, return_value=store):
            section = PendingRemindersSection()
            result = await section.build(_ctx())
        assert result is None
