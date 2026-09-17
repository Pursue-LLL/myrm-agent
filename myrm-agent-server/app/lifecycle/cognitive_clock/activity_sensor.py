"""User activity and typing sensor for cognitive clock backoff.

[INPUT]
- myrm_agent_harness.runtime.cognitive_clock.signals::get_global_pause_signal

[OUTPUT]
- UserActivitySensor: Tracks foreground user typing and interaction events.
- get_activity_sensor: Singleton getter.

[POS]
Server lifecycle tier. Bridges frontend WebSocket/HTTP activity to the harness
cooperative pause probe, ensuring background workers yield immediately on user input.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from myrm_agent_harness.runtime.cognitive_clock.signals import (
    get_global_pause_signal,
)

logger = logging.getLogger(__name__)


class UserActivitySensor:
    """Monitors real-time user interaction (typing, messages, UI actions)."""

    def __init__(self, backoff_window_seconds: float = 120.0) -> None:
        self._last_active_time: float = 0.0
        self._last_session_id: Optional[str] = None
        self._backoff_window_seconds: float = backoff_window_seconds
        self._pause_signal = get_global_pause_signal()

    def record_activity(self, session_id: Optional[str] = None, reason: str = "user_input") -> None:
        """Record an active interaction event from the user."""
        self._last_active_time = time.time()
        self._last_session_id = session_id
        # Immediately signal harness background tasks to yield at transaction boundary
        self._pause_signal.request_pause(f"{reason}:{session_id or 'anonymous'}")
        logger.debug(
            "UserActivitySensor: activity recorded for session %s (reason: %s)",
            session_id,
            reason,
        )

    def is_user_active(self) -> bool:
        """Check if user has interacted within the backoff window."""
        if self._last_active_time <= 0:
            return False
        elapsed = time.time() - self._last_active_time
        if elapsed < self._backoff_window_seconds:
            return True
        # Window expired, release pause if still set by us
        if self._pause_signal.is_pause_requested:
            self._pause_signal.clear()
        return False

    @property
    def seconds_since_last_activity(self) -> float:
        """Return elapsed seconds since last recorded user interaction."""
        if self._last_active_time <= 0:
            return 86400.0 * 365.0  # arbitrary large number
        return max(0.0, time.time() - self._last_active_time)


_GLOBAL_ACTIVITY_SENSOR: Optional[UserActivitySensor] = None


def get_activity_sensor() -> UserActivitySensor:
    """Return or initialize global UserActivitySensor singleton."""
    global _GLOBAL_ACTIVITY_SENSOR
    if _GLOBAL_ACTIVITY_SENSOR is None:
        _GLOBAL_ACTIVITY_SENSOR = UserActivitySensor()
    return _GLOBAL_ACTIVITY_SENSOR
