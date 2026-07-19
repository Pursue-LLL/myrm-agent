"""@input: lifecycle start/stop + guardian fail-closed enqueue hooks
@output: public memory guardian guard telemetry dispatcher API exports
@pos: Facade module for app.services.agent.memory_guardian_guard_telemetry subpackage.
"""

from app.services.agent.memory_guardian_guard_telemetry.dispatcher import (
    MemoryGuardianGuardTelemetryConfig,
    MemoryGuardianGuardTelemetryDispatcher,
    MemoryGuardianGuardTelemetryEvent,
    enqueue_memory_guardian_guard_telemetry,
    start_memory_guardian_guard_telemetry_dispatcher,
    stop_memory_guardian_guard_telemetry_dispatcher,
)

__all__ = [
    "MemoryGuardianGuardTelemetryConfig",
    "MemoryGuardianGuardTelemetryDispatcher",
    "MemoryGuardianGuardTelemetryEvent",
    "enqueue_memory_guardian_guard_telemetry",
    "start_memory_guardian_guard_telemetry_dispatcher",
    "stop_memory_guardian_guard_telemetry_dispatcher",
]
