"""[INPUT]
- app.channels.types::ChannelStatus (POS: Channel system domain types — pure data definitions, no I/O.)
- app.services.event.app_event_bus::AppEvent / AppEventType / get_event_bus / AppEvent / AppEventType / get_event_bus / AppEvent / AppEventType / get_event_bus (POS: Business-layer SSE bus (`ServerEventBus = PubSubBus[AppEvent]`). Kanban, memory, skills, channels publish AppEvent; api/events/router streams to WebUI clients.)

[OUTPUT]
- _on_channel_status_change: Publish channel status change events to SSE.
- _on_connection_change: Publish channel connection state change events to SSE.
- _on_groups_change: Publish groups list update events to SSE.

[POS]
channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


def _on_channel_status_change(
    channel_name: str,
    old_status: object,
    new_status: object,
) -> None:
    """Publish channel status change events to SSE."""
    from app.channels.types import ChannelStatus
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    if not isinstance(old_status, ChannelStatus) or not isinstance(new_status, ChannelStatus):
        return

    event_type: AppEventType | None = None
    if new_status != ChannelStatus.RUNNING and old_status == ChannelStatus.RUNNING:
        event_type = AppEventType.CHANNEL_DISCONNECTED

    if event_type:
        event = AppEvent(
            event_type=event_type,
            data={"channel": channel_name, "status": new_status.value},
        )
        get_event_bus().publish(event)
        logger.info("SSE: %s -> %s", event_type.value, channel_name)


def _on_connection_change(channel_name: str, connected: bool) -> None:
    """Publish channel connection state change events to SSE."""
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    event_type = AppEventType.CHANNEL_CONNECTED if connected else AppEventType.CHANNEL_DISCONNECTED
    event = AppEvent(
        event_type=event_type,
        data={
            "channel": channel_name,
            "status": "running" if connected else "disconnected",
        },
    )
    get_event_bus().publish(event)
    logger.info("SSE: %s -> %s", event_type.value, channel_name)


def _on_groups_change(channel_name: str, groups: list[object]) -> None:
    """Publish groups list update events to SSE."""
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    event = AppEvent(
        event_type=AppEventType.GROUPS_UPDATED,
        data={"channel": channel_name, "count": len(groups)},
    )
    get_event_bus().publish(event)
    logger.info("SSE: groups_updated -> %s (%d groups)", channel_name, len(groups))
