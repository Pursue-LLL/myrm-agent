"""IM Notification Dispatcher — listens to ServerEventBus and pushes to IM channels.

Subscribes to the global ServerEventBus as an independent consumer (parallel to SSE).
When a relevant event fires, loads the user's notification delivery config from
personalSettings, formats a human-readable message, and publishes it via
ChannelGateway.

[INPUT]
- app.services.event.app_event_bus::ServerEventBus, AppEvent, AppEventType
- core.channel_bridge::channel_gateway (ChannelGateway singleton)
- database.connection::get_session / database.models::UserConfigModel
- app.core.notifications.adaptive_cards::format_notification, format_legacy_text, FormattedNotification

[OUTPUT]
- NotificationDispatcher: start()/stop() lifecycle, integrates with setup.py

[POS]
Decoupled notification layer. Does NOT modify pairing_store, SSE endpoint,
or ServerEventBus — only adds a new subscriber alongside the existing SSE consumer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.channels.types import OutboundMessage
from app.channels.types.components import ComponentRow, QuickReply
from app.core.notifications.adaptive_cards import (
    FormattedNotification,
    format_legacy_text,
    format_notification,
)
from app.services.event.app_event_bus import AppEvent, ServerEventBus

logger = logging.getLogger(__name__)

_USER_ID = "local-user"


@dataclass(frozen=True, slots=True)
class NotificationTarget:
    """Resolved IM delivery target."""

    channel: str
    target: str


class NotificationDispatcher:
    """Subscribes to ServerEventBus and pushes notifications to a configured IM channel.

    Lifecycle:
      start()  — subscribe to ServerEventBus, spawn dispatch task
      stop()   — unsubscribe, cancel task
    """

    def __init__(self, event_bus: ServerEventBus) -> None:
        self._bus = event_bus
        self._queue: asyncio.Queue[AppEvent] | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._queue = self._bus.subscribe()
        self._task = asyncio.create_task(self._dispatch_loop(), name="notification-dispatcher")
        logger.info("NotificationDispatcher started")

    async def stop(self) -> None:
        if self._queue:
            try:
                self._bus.unsubscribe(self._queue)
            except Exception as e:
                logger.warning("Failed to unsubscribe from ServerEventBus: %s", e)
            self._queue = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("NotificationDispatcher task failed during stop: %s", e)
            self._task = None
        logger.info("NotificationDispatcher stopped")

    async def _dispatch_loop(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            try:
                targets = await _load_notification_targets()
                if not targets:
                    continue
                if event.data.get("suppress_im_notification") is True:
                    continue
                formatted = format_notification(event)
                if not formatted:
                    continue
                for target in targets:
                    await _publish(
                        target,
                        formatted.content,
                        components=formatted.components,
                        quick_replies=formatted.quick_replies,
                        metadata=formatted.metadata if formatted.metadata else None,
                    )
            except Exception as exc:
                logger.warning("NotificationDispatcher: failed to send IM notification: %s", exc)


async def _load_notification_targets() -> list[NotificationTarget]:
    """Read notificationDeliveries array from personalSettings in the DB."""
    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models import UserConfig

    try:
        async with get_session() as session:
            row = (
                await session.execute(
                    select(UserConfig).where(
                        UserConfig.config_key == "personalSettings",
                    )
                )
            ).scalar_one_or_none()

            if not row:
                return []

            value: dict[str, object] = row.config_value

            raw = value.get("notificationDeliveries")
            if not isinstance(raw, list):
                return []

            results: list[NotificationTarget] = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                channel = item.get("channel")
                target = item.get("target")
                if isinstance(channel, str) and isinstance(target, str) and channel and target:
                    results.append(NotificationTarget(channel=channel, target=target))
            return results
    except Exception as exc:
        logger.warning("Failed to load notification targets: %s", exc)
        return []


def _format_message(event: AppEvent) -> str | None:
    """Format an AppEvent into a human-readable notification string (legacy helper)."""
    return format_legacy_text(event)


async def _publish(
    target: NotificationTarget,
    text: str,
    components: tuple[ComponentRow, ...] = (),
    quick_replies: tuple[QuickReply, ...] = (),
    metadata: dict[str, object] | None = None,
) -> None:
    """Send a notification through the ChannelGateway with optional components and metadata."""
    from app.core.channel_bridge import channel_gateway

    msg = OutboundMessage(
        channel=target.channel,
        recipient_id=target.target,
        content=text,
        user_id=_USER_ID,
        components=components,
        quick_replies=quick_replies,
        metadata=metadata,
    )
    await channel_gateway.publish(msg)
    logger.info("IM notification sent to %s/%s", target.channel, target.target)


async def _publish_formatted(target: NotificationTarget, notif: FormattedNotification) -> None:
    """Send a structured FormattedNotification through the ChannelGateway."""
    await _publish(
        target,
        notif.content,
        components=notif.components,
        quick_replies=notif.quick_replies,
        metadata=notif.metadata if notif.metadata else None,
    )
