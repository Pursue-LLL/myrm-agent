"""IM Notification Dispatcher — listens to ServerEventBus and pushes to IM channels.

Subscribes to the global ServerEventBus as an independent consumer (parallel to SSE).
When a relevant event fires, loads the user's notification delivery config from
personalSettings, formats a human-readable message, and publishes it via
ChannelGateway.

[INPUT]
- app.services.event.app_event_bus::ServerEventBus, AppEvent, AppEventType
- core.channel_bridge::channel_gateway (ChannelGateway singleton)
- database.connection::get_session / database.models::UserConfigModel

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
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus

logger = logging.getLogger(__name__)

_USER_ID = "local-user"


@dataclass(frozen=True, slots=True)
class NotificationTarget:
    """Resolved IM delivery target."""

    channel: str
    target: str


_EVENT_TEMPLATES: dict[AppEventType, str] = {
    AppEventType.PAIRING_PENDING: (
        "[Myrm AI] New pairing request: {channel} / {sender_id}\nPlease go to Settings → Channels to approve or block."
    ),
    AppEventType.APPROVAL_REQUIRED: (
        "[Myrm AI] Approval required: {action_type} (severity: {severity})\nPlease check the app to approve or reject."
    ),
    AppEventType.HEALTH_ALERT: ("[Myrm AI] Health alert ({component}): {message}"),
    AppEventType.BUDGET_ALERT: ("[Myrm AI] Budget alert: {status} — {pct}% used (${today_cost} / ${daily_limit})"),
    AppEventType.NEW_SKILL_DRAFT: ("[Myrm AI] New skill draft '{name}' ({draft_type}) needs your review."),
    AppEventType.MESSAGE_DEAD_LETTERED: ("[Myrm AI] Message delivery failed on {channel}: {error_reason}"),
    AppEventType.CHANNEL_DISCONNECTED: (
        "[Myrm AI] Channel '{channel}' disconnected (status: {status}).\nPlease check Settings → Channels."
    ),
    AppEventType.WECHAT_SESSION_EXPIRED: ("[Myrm AI] WeChat session expired. Please re-login in Settings → Channels."),
    AppEventType.CONFIG_HEALTH_WARNING: ("[Myrm AI] Configuration issue detected.\nMissing: {missing_items}"),
    AppEventType.SYSTEM_NOTIFICATION: ("[Myrm AI] {title}: {message}"),
    AppEventType.GOAL_TERMINAL: (
        "[Myrm AI] Goal {status}: {objective}\n{files_modified} files · {total_tokens:,} tokens · ${total_cost_usd:.2f}"
    ),
    AppEventType.GOAL_DEQUEUED: ("[Myrm AI] Next goal started: {objective}"),
    AppEventType.OAUTH_REAUTH_REQUIRED: (
        "[Myrm AI] {issuer} authorization expired ({reason}).\nPlease go to Settings → Integrations to reauthorize."
    ),
}


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
                text = _format_message(event)
                if not text:
                    continue
                for target in targets:
                    await _publish(target, text)
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


_KANBAN_TERMINAL_ACTIONS = frozenset(
    {
        "task_completed",
        "task_blocked",
        "task_failed",
    }
)
_KANBAN_TERMINAL_STATUSES = frozenset(
    {
        "completed",
        "blocked",
        "failed",
    }
)


def _format_kanban_event(data: dict[str, object]) -> str | None:
    """Format a KANBAN_TASK_UPDATED event into IM notification text.

    Only terminal actions (from dispatcher) or terminal move targets
    (from KanbanService.move_task) produce notifications; high-frequency
    lifecycle events (created, updated, deleted, etc.) are silently skipped.
    """
    action = str(data.get("action", ""))
    status = str(data.get("status", ""))

    if action == "moved":
        if status not in _KANBAN_TERMINAL_STATUSES:
            return None
    elif action not in _KANBAN_TERMINAL_ACTIONS:
        return None

    title = str(data.get("title", data.get("task_id", "?")))
    detail = str(data.get("detail", ""))
    suffix = f"\n{detail[:200]}" if detail else ""

    resolved_status = status or action.removeprefix("task_")
    if resolved_status == "completed":
        return f'[Myrm AI] Kanban task "{title}" completed{suffix}'
    if resolved_status == "blocked":
        return f'[Myrm AI] Kanban task "{title}" blocked{suffix}'
    if resolved_status == "failed":
        return f'[Myrm AI] Kanban task "{title}" failed{suffix}'
    return None


def _format_message(event: AppEvent) -> str | None:
    """Format an AppEvent into a human-readable notification string."""
    if event.event_type == AppEventType.KANBAN_TASK_UPDATED:
        return _format_kanban_event(event.data)

    template = _EVENT_TEMPLATES.get(event.event_type)
    if not template:
        return None
    try:
        return template.format(**event.data)
    except (KeyError, ValueError) as exc:
        logger.warning("Failed to format notification for %s: %s", event.event_type, exc)
        return None


async def _publish(target: NotificationTarget, text: str) -> None:
    """Send the notification through the ChannelGateway."""
    from app.core.channel_bridge import channel_gateway

    msg = OutboundMessage(
        channel=target.channel,
        recipient_id=target.target,
        content=text,
        user_id=_USER_ID,
    )
    await channel_gateway.publish(msg)
    logger.info("IM notification sent to %s/%s", target.channel, target.target)
