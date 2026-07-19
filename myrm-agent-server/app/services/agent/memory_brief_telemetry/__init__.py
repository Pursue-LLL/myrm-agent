"""@input: stream_session memory brief status payloads + lifecycle start/stop hooks
@output: public memory brief telemetry dispatcher API exports
@pos: Facade module for app.services.agent.memory_brief_telemetry subpackage.
"""

from app.services.agent.memory_brief_telemetry.contract import (
    MemoryBriefStatusTelemetryConfig,
    MemoryBriefStatusTelemetryEvent,
    build_memory_brief_status_event,
)
from app.services.agent.memory_brief_telemetry.dispatcher import (
    MemoryBriefStatusTelemetryDispatcher,
    enqueue_memory_brief_status_telemetry,
    start_memory_brief_status_telemetry_dispatcher,
    stop_memory_brief_status_telemetry_dispatcher,
)

__all__ = [
    "MemoryBriefStatusTelemetryConfig",
    "MemoryBriefStatusTelemetryDispatcher",
    "MemoryBriefStatusTelemetryEvent",
    "build_memory_brief_status_event",
    "enqueue_memory_brief_status_telemetry",
    "start_memory_brief_status_telemetry_dispatcher",
    "stop_memory_brief_status_telemetry_dispatcher",
]
