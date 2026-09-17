"""Nested Multi-Frequency Cognitive Clock System.

[INPUT]
- .activity_sensor::UserActivitySensor, get_activity_sensor
- .wakeup_guard::WakeupSmoothingGuard, get_wakeup_guard
- .executors::(execute_t1_session_debounce, execute_t2_idle_maintenance, execute_t3_epoch_discovery)
- .coordinator::CognitiveClockCoordinator, get_clock_coordinator

[OUTPUT]
- High-level exports unifying T0-T3 clock management across server runtime.

[POS]
Server lifecycle tier. Central orchestration hub for cognitive evolution.
"""

from __future__ import annotations

from app.lifecycle.cognitive_clock.activity_sensor import (
    UserActivitySensor,
    get_activity_sensor,
)
from app.lifecycle.cognitive_clock.coordinator import (
    CognitiveClockCoordinator,
    get_clock_coordinator,
)
from app.lifecycle.cognitive_clock.executors import (
    execute_t1_session_debounce,
    execute_t2_idle_maintenance,
    execute_t3_epoch_discovery,
)
from app.lifecycle.cognitive_clock.wakeup_guard import (
    WakeupSmoothingGuard,
    get_wakeup_guard,
)

__all__ = [
    "UserActivitySensor",
    "get_activity_sensor",
    "WakeupSmoothingGuard",
    "get_wakeup_guard",
    "execute_t1_session_debounce",
    "execute_t2_idle_maintenance",
    "execute_t3_epoch_discovery",
    "CognitiveClockCoordinator",
    "get_clock_coordinator",
]
