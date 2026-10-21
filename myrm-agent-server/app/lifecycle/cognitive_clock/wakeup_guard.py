"""Wakeup smoothing guard for system resume / sleep detection.

[INPUT]
- None (pure system timing primitives)

[OUTPUT]
- WakeupSmoothingGuard: Suppresses heavy cognitive clock tasks during system resume storms; run_heartbeat
  gives it the cadence that makes a missed beat meaningful.
- get_wakeup_guard: Singleton getter.

[POS]
Server lifecycle tier. Prevents CPU and SQLite spikes immediately after
laptop lid opens or desktop resume from hibernation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class WakeupSmoothingGuard:
    """Detects system hibernation/sleep resume events and enforces a smoothing grace period.

    A resume shows up in one of two ways: the wall clock drifts away from the monotonic clock (the
    monotonic clock pauses while the host sleeps), or a running heartbeat misses its cadence (the
    process or host was frozen). Without a running heartbeat the time between two reads says nothing
    about the host, so only the drift signal applies.
    """

    def __init__(
        self,
        grace_period_seconds: float = 180.0,
        gap_threshold_seconds: float = 30.0,
    ) -> None:
        self._grace_period_seconds: float = grace_period_seconds
        self._gap_threshold_seconds: float = gap_threshold_seconds
        self._last_tick_wall: float = time.time()
        self._last_tick_mono: float = time.monotonic()
        self._last_wakeup_detected: float = 0.0
        self._heartbeat_running: bool = False

    @property
    def heartbeat_running(self) -> bool:
        return self._heartbeat_running

    def check_heartbeat(self) -> None:
        """Compare both clocks with the previous tick and record a resume when they disagree."""
        now_wall = time.time()
        now_mono = time.monotonic()

        wall_delta = now_wall - self._last_tick_wall
        mono_delta = now_mono - self._last_tick_mono

        clocks_drifted = abs(wall_delta - mono_delta) > self._gap_threshold_seconds
        beat_missed = self._heartbeat_running and mono_delta > self._gap_threshold_seconds * 2
        if clocks_drifted or beat_missed:
            self._last_wakeup_detected = now_wall
            logger.info(
                "WakeupSmoothingGuard: system resume/wakeup detected (wall_delta=%.1fs, mono_delta=%.1fs). "
                "Enforcing %.0fs smoothing grace period.",
                wall_delta,
                mono_delta,
                self._grace_period_seconds,
            )

        self._last_tick_wall = now_wall
        self._last_tick_mono = now_mono

    async def run_heartbeat(self, interval_seconds: Optional[float] = None) -> None:
        """Beat on a fixed cadence so that a missed beat is evidence of a frozen process or host.

        The default cadence is a third of the drift threshold, well inside the missed-beat limit.
        """
        interval = self._gap_threshold_seconds / 3 if interval_seconds is None else interval_seconds
        # The time before the first beat belongs to nobody's cadence.
        self._last_tick_wall = time.time()
        self._last_tick_mono = time.monotonic()
        self._heartbeat_running = True
        try:
            while True:
                await asyncio.sleep(interval)
                self.check_heartbeat()
        finally:
            self._heartbeat_running = False

    def is_in_grace_period(self) -> bool:
        """Return True if system is currently inside the post-wakeup smoothing window."""
        self.check_heartbeat()
        if self._last_wakeup_detected <= 0:
            return False
        elapsed = time.time() - self._last_wakeup_detected
        return elapsed < self._grace_period_seconds

    @property
    def remaining_grace_seconds(self) -> float:
        """Return remaining seconds in grace period, or 0.0 if not in grace period."""
        if not self.is_in_grace_period():
            return 0.0
        return max(0.0, self._grace_period_seconds - (time.time() - self._last_wakeup_detected))


_GLOBAL_WAKEUP_GUARD: Optional[WakeupSmoothingGuard] = None


def get_wakeup_guard() -> WakeupSmoothingGuard:
    """Return or initialize global WakeupSmoothingGuard singleton."""
    global _GLOBAL_WAKEUP_GUARD
    if _GLOBAL_WAKEUP_GUARD is None:
        _GLOBAL_WAKEUP_GUARD = WakeupSmoothingGuard()
    return _GLOBAL_WAKEUP_GUARD
