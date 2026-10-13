"""Wake-up smoothing guard: a resume is told from a quiet host by the clocks, never by an idle gap."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.lifecycle.cognitive_clock.wakeup_guard import WakeupSmoothingGuard


def _age_ticks(guard: WakeupSmoothingGuard, *, wall_seconds: float, mono_seconds: float) -> None:
    """Make the previous tick look that old on the wall clock and on the monotonic clock."""
    guard._last_tick_wall = time.time() - wall_seconds
    guard._last_tick_mono = time.monotonic() - mono_seconds


async def _stop(task: asyncio.Task[None]) -> None:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def test_a_quiet_host_after_a_long_idle_gap_is_not_a_resume() -> None:
    guard = WakeupSmoothingGuard()
    _age_ticks(guard, wall_seconds=900.0, mono_seconds=900.0)  # nobody read the guard for 15 min, both clocks agree

    assert guard.is_in_grace_period() is False
    assert guard.remaining_grace_seconds == 0.0


def test_clock_drift_marks_a_resume_however_long_the_gap() -> None:
    guard = WakeupSmoothingGuard()
    _age_ticks(guard, wall_seconds=900.0, mono_seconds=5.0)  # the monotonic clock paused while the host slept

    assert guard.is_in_grace_period() is True
    assert guard.remaining_grace_seconds > 0.0


def test_the_grace_period_ends_with_the_smoothing_window() -> None:
    guard = WakeupSmoothingGuard(grace_period_seconds=60.0)
    guard._last_wakeup_detected = time.time() - 61.0

    assert guard.is_in_grace_period() is False


@pytest.mark.asyncio
async def test_a_missed_beat_marks_a_resume_while_the_heartbeat_runs() -> None:
    guard = WakeupSmoothingGuard(grace_period_seconds=2.0, gap_threshold_seconds=0.1)
    heartbeat = asyncio.create_task(guard.run_heartbeat(interval_seconds=0.01))
    await asyncio.sleep(0)  # let the heartbeat start
    try:
        _age_ticks(guard, wall_seconds=10.0, mono_seconds=10.0)  # frozen for 10 s: both clocks advanced, no beat

        assert guard.is_in_grace_period() is True
    finally:
        await _stop(heartbeat)


@pytest.mark.asyncio
async def test_heartbeat_beats_refresh_the_ticks_without_flagging_a_resume() -> None:
    guard = WakeupSmoothingGuard()
    heartbeat = asyncio.create_task(guard.run_heartbeat(interval_seconds=0.01))
    await asyncio.sleep(0)
    try:
        _age_ticks(guard, wall_seconds=5.0, mono_seconds=5.0)  # shorter than the stall threshold
        await asyncio.sleep(0.05)  # a few beats

        assert time.monotonic() - guard._last_tick_mono < 1.0
        assert guard.is_in_grace_period() is False
    finally:
        await _stop(heartbeat)


@pytest.mark.asyncio
async def test_starting_the_heartbeat_forgets_the_time_before_it_ran() -> None:
    guard = WakeupSmoothingGuard()
    _age_ticks(guard, wall_seconds=900.0, mono_seconds=900.0)  # the guard is older than the heartbeat
    heartbeat = asyncio.create_task(guard.run_heartbeat(interval_seconds=0.01))
    await asyncio.sleep(0.03)
    try:
        assert guard.is_in_grace_period() is False
    finally:
        await _stop(heartbeat)


@pytest.mark.asyncio
async def test_a_stopped_heartbeat_does_not_read_idle_gaps_as_stalls() -> None:
    guard = WakeupSmoothingGuard()
    heartbeat = asyncio.create_task(guard.run_heartbeat(interval_seconds=0.01))
    await asyncio.sleep(0)
    assert guard.heartbeat_running is True

    await _stop(heartbeat)
    _age_ticks(guard, wall_seconds=900.0, mono_seconds=900.0)

    assert guard.heartbeat_running is False
    assert guard.is_in_grace_period() is False
