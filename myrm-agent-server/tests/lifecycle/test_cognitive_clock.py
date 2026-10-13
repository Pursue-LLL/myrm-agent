"""Comprehensive unit tests for the cognitive clock subsystem."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.runtime.cognitive_clock.signals import (
    CooperativePauseSignal,
    PauseRequestedError,
    get_global_pause_signal,
)
from myrm_agent_harness.toolkits.memory.health import HealthScore, MaintenanceReport

from app.lifecycle.cognitive_clock import executors
from app.lifecycle.cognitive_clock.activity_sensor import UserActivitySensor
from app.lifecycle.cognitive_clock.coordinator import CognitiveClockCoordinator
from app.lifecycle.cognitive_clock.executors import execute_t2_idle_maintenance, execute_t3_epoch_discovery
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


@pytest.mark.asyncio
async def test_coordinator_t2_suppressed_on_user_active() -> None:
    coordinator = CognitiveClockCoordinator()
    # The scheduler reads the guard for the first time after its 15-minute initial delay; that idle gap is no resume.
    coordinator._wakeup_guard = WakeupSmoothingGuard()
    coordinator._wakeup_guard._last_tick_wall = time.time() - 900.0
    coordinator._wakeup_guard._last_tick_mono = time.monotonic() - 900.0
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
        report, skip_reason = await coordinator.trigger_t2_cycle(force=True, policy=MemoryGuardianPolicy())
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
async def test_the_wakeup_heartbeat_runs_exactly_while_the_coordinator_runs() -> None:
    coordinator = CognitiveClockCoordinator()
    coordinator._wakeup_guard = WakeupSmoothingGuard()

    coordinator.start()
    await asyncio.sleep(0)
    try:
        assert coordinator._wakeup_guard.heartbeat_running is True
    finally:
        await coordinator.stop()

    assert coordinator._wakeup_guard.heartbeat_running is False


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


@pytest.mark.asyncio
async def test_t3_executor_reaches_the_real_pattern_discovery_cycle() -> None:
    build_llm = AsyncMock(return_value=None)

    with patch("app.lifecycle.pattern_discovery_trigger._build_platform_llm", new=build_llm):
        await execute_t3_epoch_discovery()

    build_llm.assert_awaited_once()


async def _run_one_scheduler_pass(
    coordinator: CognitiveClockCoordinator,
    t2_outcome: tuple[MaintenanceReport | None, str | None],
) -> AsyncMock:
    """Drive one pass of the scheduler loop with a stubbed T2 outcome and return the T3 stub."""
    sleeps = 0

    async def stop_after_the_pass(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:  # 1st sleep = initial delay, 2nd = the sleep that ends the pass
            raise asyncio.CancelledError()

    t3 = AsyncMock()
    with (
        patch("asyncio.sleep", side_effect=stop_after_the_pass),
        patch.object(coordinator, "trigger_t2_cycle", new=AsyncMock(return_value=t2_outcome)),
        patch("app.lifecycle.cognitive_clock.coordinator.execute_t3_epoch_discovery", new=t3),
    ):
        await coordinator._main_loop()
    return t3


@pytest.mark.asyncio
async def test_weekly_discovery_runs_when_due_and_t2_was_admitted() -> None:
    coordinator = CognitiveClockCoordinator()

    t3 = await _run_one_scheduler_pass(coordinator, (MaintenanceReport(skipped=False), None))

    t3.assert_awaited_once()
    assert coordinator._last_run_t3 > 0.0


@pytest.mark.asyncio
async def test_weekly_discovery_waits_while_the_budget_blocks_background_work() -> None:
    coordinator = CognitiveClockCoordinator()

    t3 = await _run_one_scheduler_pass(coordinator, (None, "budget_blocked"))

    t3.assert_not_awaited()
    assert coordinator._last_run_t3 == 0.0


@pytest.mark.asyncio
async def test_weekly_discovery_is_not_repeated_before_the_week_is_up() -> None:
    coordinator = CognitiveClockCoordinator()
    coordinator._last_run_t3 = time.time()

    t3 = await _run_one_scheduler_pass(coordinator, (MaintenanceReport(skipped=False), None))

    t3.assert_not_awaited()


# --- T2 maintenance pipeline: leaf steps are autospecced so a wrong call signature fails the cycle ---

_T2_STEP_RESULTS: dict[str, object] = {
    "purge_expired_archives": 2,
    "auto_resolve_expired_conflicts": 1,
    "harvest_session_blind_spots": 0,
    "sync_external_harness_transcripts": 0,
    "record_purge_audit": None,
    "record_conflict_auto_resolve_event": None,
    "record_maintenance_event": None,
    "record_health_snapshot": None,
    "run_sqlite_backup": None,
}


@contextmanager
def _patched_t2_steps(report: MaintenanceReport) -> Iterator[dict[str, AsyncMock]]:
    """Replace every T2 step with a signature-enforcing stub and yield them by name."""
    manager = AsyncMock()
    manager.run_maintenance_cycle.return_value = report
    results = {"create_guardian_memory_manager": manager, **_T2_STEP_RESULTS}
    with ExitStack() as stack:
        yield {
            name: stack.enter_context(patch.object(executors, name, autospec=True, return_value=value))
            for name, value in results.items()
        }


def _healthy_report() -> MaintenanceReport:
    health = HealthScore(total=90, dimensions={}, suggestions=[], has_graph=False, sample_size=10)
    return MaintenanceReport(skipped=False, health=health)


@pytest.mark.asyncio
async def test_t2_pipeline_runs_every_step_and_hands_back_the_report() -> None:
    report = _healthy_report()
    policy = MemoryGuardianPolicy()

    with _patched_t2_steps(report) as steps:
        outcome, error = await execute_t2_idle_maintenance(force=True, policy=policy)

    assert error is None
    assert outcome is report
    steps["record_purge_audit"].assert_awaited_once_with(purged_count=2, policy=policy)
    steps["record_conflict_auto_resolve_event"].assert_awaited_once_with(resolved_count=1, policy=policy)
    steps["record_maintenance_event"].assert_awaited_once_with(report=report, forced=True, policy=policy)
    steps["record_health_snapshot"].assert_awaited_once_with(report, policy=policy, guardian_running=True)
    steps["run_sqlite_backup"].assert_awaited_once_with()


@pytest.mark.asyncio
async def test_t2_pipeline_stops_after_a_skipped_maintenance_cycle() -> None:
    report = MaintenanceReport(skipped=True, skip_reason="not_enough_memories")

    with _patched_t2_steps(report) as steps:
        outcome, reason = await execute_t2_idle_maintenance(force=False, policy=MemoryGuardianPolicy())

    assert outcome is report
    assert reason == "not_enough_memories"
    for name in _T2_STEP_RESULTS:
        steps[name].assert_not_awaited()
