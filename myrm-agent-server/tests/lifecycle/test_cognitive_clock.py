"""Comprehensive unit tests for the cognitive clock subsystem."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.runtime.cognitive_clock.signals import (
    CooperativePauseSignal,
    PauseRequestedError,
    get_global_pause_signal,
)
from myrm_agent_harness.toolkits.memory.health import MaintenanceReport

from app.lifecycle.cognitive_clock.activity_sensor import UserActivitySensor
from app.lifecycle.cognitive_clock.coordinator import CognitiveClockCoordinator
from app.lifecycle.cognitive_clock.wakeup_guard import WakeupSmoothingGuard
from app.services.memory.ledger.guardian_policy import MemoryGuardianPolicy


def test_cooperative_pause_signal_flow() -> None:
    signal = CooperativePauseSignal()
    assert signal.is_pause_requested is False

    signal.request_pause("user typing")
    assert signal.is_pause_requested is True
    assert signal.pause_reason == "user typing"

    with pytest.raises(PauseRequestedError):
        signal.raise_if_paused()

    signal.checkpoint_cursor("cursor_offset_100")
    assert signal.cursor == "cursor_offset_100"

    signal.clear()
    assert signal.is_pause_requested is False


def test_user_activity_sensor_triggers_pause() -> None:
    sensor = UserActivitySensor(backoff_window_seconds=1.0)
    assert sensor.is_user_active() is False

    sensor.record_activity(session_id="test_sess", reason="key_press")
    assert sensor.is_user_active() is True
    assert get_global_pause_signal().is_pause_requested is True

    # After sleeping > window
    time.sleep(1.05)
    assert sensor.is_user_active() is False
    assert get_global_pause_signal().is_pause_requested is False


def test_wakeup_smoothing_guard_detects_gap() -> None:
    guard = WakeupSmoothingGuard(grace_period_seconds=2.0, gap_threshold_seconds=0.1)
    # Simulate time stall
    guard._last_tick_wall = time.time() - 10.0
    guard._last_tick_mono = time.monotonic() - 10.0
    guard.check_heartbeat()

    assert guard.is_in_grace_period() is True
    assert guard.remaining_grace_seconds > 0.0


@pytest.mark.asyncio
async def test_coordinator_t2_suppressed_on_user_active() -> None:
    coordinator = CognitiveClockCoordinator()
    coordinator._activity_sensor.record_activity(session_id="active_sess", reason="chat_input")

    report, skip_reason = await coordinator.trigger_t2_cycle(force=False)
    assert report is None
    assert skip_reason == "user_active"


@pytest.mark.asyncio
async def test_coordinator_t2_suppressed_on_wakeup_grace() -> None:
    coordinator = CognitiveClockCoordinator()
    # Clear activity
    coordinator._activity_sensor._last_active_time = 0.0
    coordinator._activity_sensor._pause_signal.clear()

    # Simulate wakeup
    coordinator._wakeup_guard._last_wakeup_detected = time.time()
    coordinator._wakeup_guard._grace_period_seconds = 100.0

    report, skip_reason = await coordinator.trigger_t2_cycle(force=False)
    assert report is None
    assert skip_reason == "wakeup_smoothing_active"


@pytest.mark.asyncio
async def test_coordinator_t2_runs_when_clean() -> None:
    coordinator = CognitiveClockCoordinator()
    coordinator._activity_sensor._last_active_time = 0.0
    coordinator._activity_sensor._pause_signal.clear()
    coordinator._wakeup_guard._last_wakeup_detected = 0.0

    fake_report = MaintenanceReport(
        skipped=False,
        consolidation_merged=2,
        consolidation_corrected=1,
        forgotten_count=0,
        archived_count=0,
        duration_ms=50.0,
    )

    with patch(
        "app.lifecycle.cognitive_clock.coordinator.execute_t2_idle_maintenance",
        new=AsyncMock(return_value=(fake_report, None)),
    ):
        report, skip_reason = await coordinator.trigger_t2_cycle(
            force=True, policy=MemoryGuardianPolicy()
        )
        assert report is fake_report
        assert skip_reason is None
        assert coordinator._last_run_t2 is not None


@pytest.mark.asyncio
async def test_coordinator_skip_tracking_and_status() -> None:
    coordinator = CognitiveClockCoordinator()
    coordinator._activity_sensor.record_activity(session_id="s1", reason="typing")

    report, skip_reason = await coordinator.trigger_t2_cycle(force=False)
    assert report is None
    assert skip_reason == "user_active"
    assert coordinator._last_skip_reason == "user_active"
    assert coordinator._consecutive_skips == 1

    status = await coordinator.get_status()
    assert status["last_skip_reason"] == "user_active"
    assert status["consecutive_skips"] == 1

    # Now succeed
    fake_report = MaintenanceReport(skipped=False)
    with patch(
        "app.lifecycle.cognitive_clock.coordinator.execute_t2_idle_maintenance",
        new=AsyncMock(return_value=(fake_report, None)),
    ):
        await coordinator.trigger_t2_cycle(force=True)
        assert coordinator._last_skip_reason is None
        assert coordinator._consecutive_skips == 0


@pytest.mark.asyncio
async def test_coordinator_main_loop_fast_retry_on_suppression() -> None:
    coordinator = CognitiveClockCoordinator()
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError()

    with (
        patch("asyncio.sleep", side_effect=fake_sleep),
        patch.object(coordinator, "trigger_t2_cycle", new=AsyncMock(return_value=(None, "user_active"))),
    ):
        await coordinator._main_loop()

    # The first sleep is _INITIAL_DELAY_MINUTES * 60 (900s)
    # The second sleep should be _QUIET_WINDOW_RECHECK_SECONDS (900s) due to fast retry
    assert len(sleep_calls) == 2
    assert sleep_calls[0] == 900.0
    assert sleep_calls[1] == 900.0

