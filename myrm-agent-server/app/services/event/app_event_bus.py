"""Global in-process event bus for real-time SSE notifications.

[INPUT]
- myrm_agent_harness.infra.pubsub.event_bus::PubSubBus (POS: Harness generic pub/sub)

[OUTPUT]
- AppEventType, AppEvent, get_event_bus: Server-side SSE event bus singleton

[POS]
Business-layer event bus. Kanban, memory, skills, channels publish AppEvent;
api/events/router streams to WebUI clients. Must not live under app/api/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from myrm_agent_harness.infra.pubsub.event_bus import PubSubBus


class AppEventType(StrEnum):
    """Known event types pushed to web clients."""

    PAIRING_PENDING = "pairing_pending"
    WECHAT_SESSION_EXPIRED = "wechat_session_expired"
    CHANNEL_CONNECTED = "channel_connected"
    CHANNEL_DISCONNECTED = "channel_disconnected"
    GROUPS_UPDATED = "groups_updated"
    SKILL_INSTALL_PROGRESS = "skill_install_progress"
    CONFIG_HEALTH_WARNING = "config_health_warning"
    AGENT_CONFIG_UPDATED = "agent_config_updated"
    MESSAGE_DEAD_LETTERED = "message_dead_lettered"
    NEW_SKILL_DRAFT = "new_skill_draft"
    SKILL_GROWTH_UPDATED = "skill_growth_updated"
    SKILL_EVOLVED = "skill_evolved"
    SYSTEM_NOTIFICATION = "system_notification"
    IDLE_STATUS = "idle_status"
    APPROVAL_REQUIRED = "approval_required"
    STATUS = "status"
    HEALTH_ALERT = "health_alert"
    BUDGET_ALERT = "budget_alert"
    ASYNC_AGENT_STREAM_CHUNK = "async_agent_stream_chunk"
    BENCHMARK_PROGRESS = "benchmark_progress"
    MEMORY_HISTORY_UPDATED = "memory_history_updated"
    MEMORY_OPERATION = "memory_operation"
    SUBAGENTS_UPDATED = "subagents_updated"
    TEAMMATE_MESSAGE = "teammate_message"
    APPROVAL_RESOLVED = "approval_resolved"
    CRON_UPDATED = "cron_updated"
    SKILL_AB_TEST_UPDATED = "skill_ab_test_updated"
    HEALTH_STATUS_UPDATED = "health_status_updated"
    BUDGET_UPDATED = "budget_updated"
    CHANNEL_STATUS_UPDATED = "channel_status_updated"
    SKILL_QUALITY_UPDATED = "skill_quality_updated"
    KANBAN_TASK_UPDATED = "kanban_task_updated"
    BACKGROUND_TASK_DONE = "background_task_done"
    UX_WARNING_TRUNCATED = "ux_warning_truncated"
    LOCATOR_HEALED = "locator_healed"
    GOAL_TERMINAL = "goal_terminal"
    GOAL_DEQUEUED = "goal_dequeued"
    EXTENSION_STATUS_CHANGED = "extension_status_changed"


@dataclass(frozen=True, slots=True)
class AppEvent:
    """Immutable event payload broadcast to all SSE subscribers."""

    event_type: AppEventType
    data: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


ServerEventBus = PubSubBus[AppEvent]

_bus: ServerEventBus | None = None


def get_event_bus() -> ServerEventBus:
    """Singleton accessor — lazily created on first call."""
    global _bus  # noqa: PLW0603
    if _bus is None:
        _bus = PubSubBus()
    return _bus
