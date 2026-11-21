"""Unit tests for CronManager updates: patch application, monitor-baseline auto-reset and the manual baseline reset."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronJob,
    CronJobPatch,
    DeliveryConfig,
    FailureAlertConfig,
    JobType,
    SessionTarget,
)
from tests.support.cron_manager_mocks import make_job, make_manager

# ---------------------------------------------------------------------------
# update_job — patch application for all clear_xxx patterns
# ---------------------------------------------------------------------------


class TestUpdateJobPatch:
    @pytest.fixture()
    def mgr(self) -> CronManager:
        return make_manager()

    async def _do_update(self, mgr: CronManager, job: CronJob, patch: CronJobPatch) -> CronJob:
        mgr._store.get_job = AsyncMock(return_value=job)
        result = await mgr.update_job(job.id, patch)
        assert result is not None
        return result

    # --- clear_max_fires ---

    @pytest.mark.asyncio
    async def test_clear_max_fires(self, mgr: CronManager):
        job = make_job(max_fires=100)
        result = await self._do_update(mgr, job, CronJobPatch(clear_max_fires=True))
        assert result.max_fires is None

    @pytest.mark.asyncio
    async def test_set_max_fires(self, mgr: CronManager):
        job = make_job(max_fires=None)
        result = await self._do_update(mgr, job, CronJobPatch(max_fires=50))
        assert result.max_fires == 50

    @pytest.mark.asyncio
    async def test_clear_max_fires_takes_precedence(self, mgr: CronManager):
        job = make_job(max_fires=100)
        result = await self._do_update(mgr, job, CronJobPatch(clear_max_fires=True, max_fires=50))
        assert result.max_fires is None

    # --- clear_expires_at ---

    @pytest.mark.asyncio
    async def test_clear_expires_at(self, mgr: CronManager):
        dt = datetime(2026, 12, 31, tzinfo=UTC)
        job = make_job(expires_at=dt)
        result = await self._do_update(mgr, job, CronJobPatch(clear_expires_at=True))
        assert result.expires_at is None

    @pytest.mark.asyncio
    async def test_set_expires_at(self, mgr: CronManager):
        dt = datetime(2027, 6, 15, tzinfo=UTC)
        job = make_job(expires_at=None)
        result = await self._do_update(mgr, job, CronJobPatch(expires_at=dt))
        assert result.expires_at == dt

    # --- clear_failure_alert ---

    @pytest.mark.asyncio
    async def test_clear_failure_alert(self, mgr: CronManager):
        fa = FailureAlertConfig(after=5)
        job = make_job(failure_alert=fa)
        result = await self._do_update(mgr, job, CronJobPatch(clear_failure_alert=True))
        assert result.failure_alert is False

    @pytest.mark.asyncio
    async def test_set_failure_alert(self, mgr: CronManager):
        fa = FailureAlertConfig(after=10, cooldown_seconds=1200)
        job = make_job(failure_alert=None)
        result = await self._do_update(mgr, job, CronJobPatch(failure_alert=fa))
        assert result.failure_alert == fa

    # --- clear_failure_delivery ---

    @pytest.mark.asyncio
    async def test_clear_failure_delivery(self, mgr: CronManager):
        d = DeliveryConfig(channel="webhook", target="https://x.com")
        job = make_job(failure_delivery=d)
        result = await self._do_update(mgr, job, CronJobPatch(clear_failure_delivery=True))
        assert result.failure_delivery is None

    @pytest.mark.asyncio
    async def test_set_failure_delivery(self, mgr: CronManager):
        d = DeliveryConfig(channel="webhook", target="https://y.com")
        job = make_job(failure_delivery=None)
        result = await self._do_update(mgr, job, CronJobPatch(failure_delivery=d))
        assert result.failure_delivery == d

    # --- clear_active_hours ---

    @pytest.mark.asyncio
    async def test_clear_active_hours(self, mgr: CronManager):
        ah = ActiveHours(start="09:00", end="18:00")
        job = make_job(active_hours=ah)
        result = await self._do_update(mgr, job, CronJobPatch(clear_active_hours=True))
        assert result.active_hours is None

    # --- clear_last_error ---

    @pytest.mark.asyncio
    async def test_clear_last_error(self, mgr: CronManager) -> None:
        job = make_job(last_error="HTTP 500: upstream unavailable")
        result = await self._do_update(mgr, job, CronJobPatch(clear_last_error=True))
        assert result.last_error is None

    # --- cooldown_seconds ---

    @pytest.mark.asyncio
    async def test_set_cooldown(self, mgr: CronManager):
        job = make_job(cooldown_seconds=0)
        result = await self._do_update(mgr, job, CronJobPatch(cooldown_seconds=120))
        assert result.cooldown_seconds == 120

    # --- session_target ---

    @pytest.mark.asyncio
    async def test_set_session_target(self, mgr: CronManager):
        job = make_job(session_target=SessionTarget.ISOLATED)
        result = await self._do_update(mgr, job, CronJobPatch(session_target=SessionTarget.MAIN))
        assert result.session_target == SessionTarget.MAIN

    # --- chat_id ---

    @pytest.mark.asyncio
    async def test_set_chat_id(self, mgr: CronManager):
        job = make_job(session_target=SessionTarget.MAIN, chat_id=None)
        result = await self._do_update(mgr, job, CronJobPatch(chat_id="chat-new"))
        assert result.chat_id == "chat-new"

    @pytest.mark.asyncio
    async def test_change_chat_id(self, mgr: CronManager):
        job = make_job(session_target=SessionTarget.MAIN, chat_id="chat-old")
        result = await self._do_update(mgr, job, CronJobPatch(chat_id="chat-new"))
        assert result.chat_id == "chat-new"

    @pytest.mark.asyncio
    async def test_clear_chat_id(self, mgr: CronManager):
        job = make_job(session_target=SessionTarget.ISOLATED, chat_id="chat-old")
        result = await self._do_update(mgr, job, CronJobPatch(clear_chat_id=True))
        assert result.chat_id is None

    @pytest.mark.asyncio
    async def test_empty_patch_preserves_chat_id(self, mgr: CronManager):
        job = make_job(session_target=SessionTarget.MAIN, chat_id="chat-keep")
        result = await self._do_update(mgr, job, CronJobPatch())
        assert result.chat_id == "chat-keep"

    # --- run_retention_days ---

    @pytest.mark.asyncio
    async def test_set_run_retention_days(self, mgr: CronManager):
        job = make_job(run_retention_days=30)
        result = await self._do_update(mgr, job, CronJobPatch(run_retention_days=90))
        assert result.run_retention_days == 90

    # --- delete_after_run ---

    @pytest.mark.asyncio
    async def test_set_delete_after_run(self, mgr: CronManager):
        job = make_job(delete_after_run=False)
        result = await self._do_update(mgr, job, CronJobPatch(delete_after_run=True))
        assert result.delete_after_run is True

    # --- missing job ---

    @pytest.mark.asyncio
    async def test_missing_job_returns_none(self, mgr: CronManager):
        mgr._store.get_job = AsyncMock(return_value=None)
        result = await mgr.update_job("nonexistent", CronJobPatch(name="x"))
        assert result is None

    # --- empty patch ---

    @pytest.mark.asyncio
    async def test_empty_patch_preserves_all(self, mgr: CronManager):
        dt = datetime(2026, 12, 31, tzinfo=UTC)
        fa = FailureAlertConfig(after=5)
        job = make_job(
            cooldown_seconds=60,
            max_fires=100,
            expires_at=dt,
            session_target=SessionTarget.MAIN,
            failure_alert=fa,
            run_retention_days=90,
            last_error="HTTP 500: upstream unavailable",
        )
        result = await self._do_update(mgr, job, CronJobPatch())
        assert result.cooldown_seconds == 60
        assert result.max_fires == 100
        assert result.expires_at == dt
        assert result.session_target == SessionTarget.MAIN
        assert result.failure_alert == fa
        assert result.run_retention_days == 90
        assert result.last_error == "HTTP 500: upstream unavailable"


# ---------------------------------------------------------------------------
# update_job — monitor baseline auto-reset
# ---------------------------------------------------------------------------


class TestUpdateJobMonitorReset:
    @pytest.mark.asyncio
    async def test_prompt_change_resets_baseline(self) -> None:
        from myrm_agent_harness.infra.incremental.types import MonitorConfig, MonitorState

        mgr = make_manager()
        mc = MonitorConfig(enabled=True, monitor_type="text_diff")
        job = make_job(prompt="old prompt", monitor_config=mc)
        state = MonitorState(job_id="job-1", monitor_type="text_diff", data={"old": True})
        mgr._store.get_job = AsyncMock(return_value=job)
        mgr._store.get_monitor_state = AsyncMock(return_value=state)
        result = await mgr.update_job("job-1", CronJobPatch(prompt="new prompt"))
        assert result is not None
        assert result.prompt == "new prompt"
        mgr._store.save_monitor_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_command_change_resets_baseline(self) -> None:
        from myrm_agent_harness.infra.incremental.types import MonitorConfig, MonitorState

        mgr = make_manager()
        mc = MonitorConfig(enabled=True, monitor_type="text_diff")
        job = make_job(job_type=JobType.SHELL, command="echo old", monitor_config=mc, prompt=None)
        state = MonitorState(job_id="job-1", monitor_type="text_diff", data={"old": True})
        mgr._store.get_job = AsyncMock(return_value=job)
        mgr._store.get_monitor_state = AsyncMock(return_value=state)
        result = await mgr.update_job("job-1", CronJobPatch(command="echo new"))
        assert result is not None
        mgr._store.save_monitor_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deduplicate_clear_resets_hash(self) -> None:
        mgr = make_manager()
        job = make_job(deduplicate=True, last_output_hash="abc123")
        mgr._store.get_job = AsyncMock(return_value=job)
        result = await mgr.update_job("job-1", CronJobPatch(deduplicate=False))
        assert result is not None
        assert result.deduplicate is False
        assert result.last_output_hash is None

    @pytest.mark.asyncio
    async def test_clear_monitor_config(self) -> None:
        from myrm_agent_harness.infra.incremental.types import MonitorConfig

        mgr = make_manager()
        mc = MonitorConfig(enabled=True, monitor_type="text_diff")
        job = make_job(monitor_config=mc)
        mgr._store.get_job = AsyncMock(return_value=job)
        result = await mgr.update_job("job-1", CronJobPatch(clear_monitor_config=True))
        assert result is not None
        assert result.monitor_config is None


# ---------------------------------------------------------------------------
# reset_monitor_baseline
# ---------------------------------------------------------------------------


class TestResetMonitorBaseline:
    @pytest.mark.asyncio
    async def test_reset_success(self) -> None:
        from myrm_agent_harness.infra.incremental.types import MonitorState

        mgr = make_manager()
        job = make_job()
        state = MonitorState(job_id="job-1", monitor_type="text_diff", data={"some": "data"})
        mgr._store.get_job = AsyncMock(return_value=job)
        mgr._store.get_monitor_state = AsyncMock(return_value=state)
        assert await mgr.reset_monitor_baseline("job-1") is True
        assert state.data == {}
        assert state.last_reset_reason == "manual"
        mgr._store.save_monitor_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reset_no_state(self) -> None:
        mgr = make_manager()
        job = make_job()
        mgr._store.get_job = AsyncMock(return_value=job)
        mgr._store.get_monitor_state = AsyncMock(return_value=None)
        assert await mgr.reset_monitor_baseline("job-1") is False

    @pytest.mark.asyncio
    async def test_reset_job_not_found(self) -> None:
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=None)
        assert await mgr.reset_monitor_baseline("job-1") is False
        mgr._store.save_monitor_state.assert_not_awaited()
