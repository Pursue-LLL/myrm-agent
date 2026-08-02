"""GoalTerminalNotifier — pushes Goal completion results back to the originating IM channel.

Subscribes to the global ServerEventBus and filters for GOAL_TERMINAL events
that carry source channel metadata (injected by goal_handler._set_goal).
For each matching event it sends a localised summary to the channel/chat_id/thread_id
stored in the Goal metadata, using the existing ``send_with_retry`` infrastructure.

Only IM-originated Goals carry source metadata; WebUI and Cron Goals are silently
skipped (no channel info → no delivery target).

[INPUT]
- services.event.app_event_bus::ServerEventBus, AppEvent, AppEventType
- core.channel_bridge::channel_gateway

[OUTPUT]
- GoalTerminalNotifier: start()/stop() lifecycle, registered in setup.py

[POS]
Business-layer ServerEventBus subscriber. Mirrors BtwTaskNotifier pattern for
Goal lifecycle — does NOT modify the Goal pipeline, dispatcher, or harness layer.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.channels.i18n import channel_t
from app.channels.types import OutboundMessage
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus

logger = logging.getLogger(__name__)


class GoalTerminalNotifier:
    """Delivers Goal completion results to the IM channel that spawned them."""

    def __init__(self, event_bus: ServerEventBus) -> None:
        self._bus = event_bus
        self._queue: asyncio.Queue[AppEvent] | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._queue = self._bus.subscribe()
        self._task = asyncio.create_task(self._loop(), name="goal-terminal-notifier")
        logger.info("GoalTerminalNotifier started")

    async def stop(self) -> None:
        if self._queue:
            try:
                self._bus.unsubscribe(self._queue)
            except Exception as exc:
                logger.warning("Failed to unsubscribe GoalTerminalNotifier: %s", exc)
            self._queue = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("GoalTerminalNotifier task error during stop: %s", exc)
            self._task = None
        logger.info("GoalTerminalNotifier stopped")

    async def _loop(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            if event.event_type != AppEventType.GOAL_TERMINAL:
                continue
            if not event.data.get("channel"):
                continue
            try:
                await self._deliver(event.data)
            except Exception as exc:
                logger.warning("GoalTerminalNotifier delivery failed: %s", exc, exc_info=True)

    async def _deliver(self, data: dict[str, object]) -> None:
        from app.channels.core.bus import downgrade_components
        from app.channels.reliability.retry import send_with_retry
        from app.channels.types.status import ChannelStatus
        from app.core.channel_bridge import channel_gateway

        channel_name = str(data.get("channel", ""))
        chat_id = str(data.get("chat_id", ""))
        if not channel_name or not chat_id:
            return

        channel = channel_gateway.bus.channels.get(channel_name)
        if not channel:
            logger.debug("GoalTerminalNotifier: channel '%s' not registered, skipping", channel_name)
            return
        if channel.status in (ChannelStatus.DISABLED, ChannelStatus.STOPPED):
            logger.debug("GoalTerminalNotifier: channel '%s' is %s, skipping", channel_name, channel.status)
            return

        status = str(data.get("status", ""))
        objective = str(data.get("objective", ""))
        locale = str(data.get("locale", "en"))
        content = _format_goal_notification(data, status, objective, locale)

        thread_id = str(data.get("thread_id", "")) or None
        metadata: dict[str, object] = {}
        if thread_id:
            metadata["thread_id"] = thread_id

        components: tuple[tuple[object, ...], ...] = ()
        session_id = str(data.get("session_id", ""))
        if session_id:
            try:
                from app.remote_access.mobile_deep_link import resolve_web_handoff_components

                components = await resolve_web_handoff_components(session_id, locale=locale)
            except Exception:
                logger.debug("Failed to resolve web handoff for goal notification, skipping")

        msg = OutboundMessage(
            channel=channel_name,
            recipient_id=chat_id,
            content=content,
            user_id="local-user",
            metadata=metadata if metadata else None,
            components=components or None,
        )

        msg = downgrade_components(msg, channel)
        t0 = time.monotonic()
        try:
            await send_with_retry(
                channel.send,
                msg,
                config=channel.retry_config,
                should_retry=channel.should_retry,
                extract_retry_after=channel.extract_retry_after,
                label=f"goal-notify:{channel_name}",
            )
            channel.activity.record_outbound(latency_ms=(time.monotonic() - t0) * 1000)
            logger.info("Goal result delivered to %s/%s", channel_name, chat_id)
        except Exception as exc:
            channel.activity.record_error()
            logger.warning("Failed to deliver goal result to %s/%s: %s", channel_name, chat_id, exc, exc_info=True)


def _format_goal_notification(
    data: dict[str, object],
    status: str,
    objective: str,
    locale: str,
) -> str:
    preview = objective[:120] if objective else "goal"
    turns = data.get("turns_used", 0)
    duration_s = float(data.get("execution_duration_s", 0))
    files = data.get("files_modified", 0)

    duration_min = round(duration_s / 60, 1) if duration_s > 0 else 0

    key = "goal_completed" if status == "complete" else "goal_failed"
    return channel_t(
        locale,
        key,
        objective=preview,
        turns=turns,
        duration=duration_min,
        files=files,
    ).strip()
