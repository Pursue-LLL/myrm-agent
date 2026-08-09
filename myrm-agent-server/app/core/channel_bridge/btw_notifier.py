"""BtwTaskNotifier — pushes /btw task results back to the originating channel.

Subscribes to the global ServerEventBus and filters for BACKGROUND_TASK_DONE events
(published by ``_emit_btw_done`` in the Kanban service). For each event it
sends a localised summary to the channel/chat_id/thread_id stored in the
task metadata, using the existing ``send_with_retry`` infrastructure.

Runs in parallel with ``NotificationDispatcher`` (which handles
user-configured notification targets); this notifier specifically addresses
the "reply in the original conversation" use case.

[INPUT]
- services.event.app_event_bus::ServerEventBus, AppEvent, AppEventType
- core.channel_bridge::channel_gateway

[OUTPUT]
- BtwTaskNotifier: start()/stop() lifecycle, registered in setup.py

[POS]
Business-layer ServerEventBus subscriber. Does NOT modify the Kanban pipeline,
dispatcher callbacks, or NotificationDispatcher.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.channels.i18n import channel_t
from app.channels.types import OutboundMessage
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus

logger = logging.getLogger(__name__)


class BtwTaskNotifier:
    """Delivers /btw task results to the channel that spawned them."""

    def __init__(self, event_bus: ServerEventBus) -> None:
        self._bus = event_bus
        self._queue: asyncio.Queue[AppEvent] | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._queue = self._bus.subscribe()
        self._task = asyncio.create_task(self._loop(), name="btw-task-notifier")
        logger.info("BtwTaskNotifier started")

    async def stop(self) -> None:
        if self._queue:
            try:
                self._bus.unsubscribe(self._queue)
            except Exception as exc:
                logger.warning("Failed to unsubscribe BtwTaskNotifier: %s", exc)
            self._queue = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("BtwTaskNotifier task error during stop: %s", exc)
            self._task = None
        logger.info("BtwTaskNotifier stopped")

    async def _loop(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            if event.event_type != AppEventType.BACKGROUND_TASK_DONE:
                continue
            await self._deliver(event.data)

    async def _deliver(self, data: dict[str, object]) -> None:
        from app.channels.core.bus import downgrade_components
        from app.channels.reliability.retry import send_with_retry
        from app.channels.types.status import ChannelStatus
        from app.core.channel_bridge import channel_gateway

        channel_name = str(data.get("channel", ""))
        chat_id = str(data.get("chat_id", ""))
        thread_id = str(data.get("thread_id", "")) or None
        locale = str(data.get("locale", "en"))

        if not channel_name or not chat_id:
            resolved = await self._resolve_im_target(data)
            if resolved is None:
                return
            channel_name, chat_id, thread_id, locale = resolved

        status = str(data.get("status", ""))
        title = str(data.get("title", ""))
        result = str(data.get("result", ""))
        content = _format_notification(status, title, result, locale)
        task_id = str(data.get("task_id", ""))

        metadata: dict[str, object] = {}
        if thread_id:
            metadata["thread_id"] = thread_id

        user_id = str(data.get("user_id", "")) or "local-user"

        components: tuple[tuple[object, ...], ...] = ()
        if task_id:
            try:
                from app.channels.routing.router_keys import routing_session_key
                from app.remote_access.mobile_deep_link import (
                    resolve_web_handoff_components,
                )
                from app.services.chat.chat_service import ChatService

                session_key = routing_session_key(channel_name, chat_id)
                chat = await ChatService.get_channel_chat_by_key(session_key)
                if chat:
                    components = await resolve_web_handoff_components(
                        chat.id,
                        locale=locale,
                    )
            except Exception:
                logger.debug(
                    "Failed to resolve web handoff for btw notification, skipping"
                )

        msg = OutboundMessage(
            channel=channel_name,
            recipient_id=chat_id,
            content=content,
            user_id=user_id,
            metadata=metadata if metadata else None,
            components=components or None,
        )

        channel = channel_gateway.bus.channels.get(channel_name)
        if not channel:
            logger.debug(
                "BtwTaskNotifier: channel '%s' not registered, skipping", channel_name
            )
            return
        if channel.status in (ChannelStatus.DISABLED, ChannelStatus.STOPPED):
            logger.debug(
                "BtwTaskNotifier: channel '%s' is %s, skipping",
                channel_name,
                channel.status,
            )
            return

        msg = downgrade_components(msg, channel)
        t0 = time.monotonic()
        try:
            await send_with_retry(
                channel.send,
                msg,
                config=channel.retry_config,
                should_retry=channel.should_retry,
                extract_retry_after=channel.extract_retry_after,
                label=f"btw-notify:{channel_name}",
            )
            channel.activity.record_outbound(latency_ms=(time.monotonic() - t0) * 1000)
            logger.info("Btw task result delivered to %s/%s", channel_name, chat_id)
        except Exception as exc:
            channel.activity.record_error()
            logger.warning(
                "Failed to deliver btw result to %s/%s: %s",
                channel_name,
                chat_id,
                exc,
                exc_info=True,
            )

    async def _resolve_im_target(
        self,
        data: dict[str, object],
    ) -> tuple[str, str, str | None, str] | None:
        """Resolve IM channel delivery target from source_chat_id when channel metadata is absent."""
        source_chat_id = str(
            data.get("source_chat_id", "") or data.get("chat_id", "")
        ).strip()
        if not source_chat_id:
            return None

        locale = str(data.get("locale", "en"))
        try:
            from app.channels.types.session import SessionKey
            from app.services.chat.chat_service import ChatService

            chat = await ChatService.get_chat_by_id(source_chat_id)
            if chat is None:
                return None
            if chat.source == "web" or not chat.channel_session_key:
                return None

            raw_key = chat.channel_session_key.split(":e=")[0]
            session_key = SessionKey.parse(raw_key)
            if session_key is None or not session_key.peer_id:
                return None

            thread_id = str(data.get("thread_id", "")) or None
            return session_key.channel, session_key.peer_id, thread_id, locale
        except Exception:
            logger.debug(
                "Failed to resolve IM target for source_chat_id=%s",
                source_chat_id,
                exc_info=True,
            )
            return None


def _format_notification(
    status: str, title: str, result: str, locale: str = "en"
) -> str:
    preview = title[:80] if title else "background task"
    summary = result[:300] if result else ""

    if status == "completed":
        key = "background_completed"
    elif status == "blocked":
        key = "background_blocked"
    elif status == "pending_review":
        key = "background_pending_review"
    elif status == "rejected":
        key = "background_rejected"
    else:
        key = "background_failed"
    return channel_t(locale, key, title=preview, result=summary).strip()
