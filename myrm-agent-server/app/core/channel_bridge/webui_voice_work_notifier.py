"""WebUI voice background work completion — chat transcript + SSE for voice-spawned Kanban tasks.

[INPUT]
- app.services.event.app_event_bus::ServerEventBus, AppEvent, AppEventType (POS: global SSE bus)
- app.services.chat.chat_service::ChatService (POS: message persistence)
- app.core.channel_bridge.btw_notifier::_format_notification (POS: i18n notification body)
- app.core.channel_bridge.persistent_background::BACKGROUND_SOURCE_VOICE (POS: voice spawn marker)

[OUTPUT]
- WebuiVoiceWorkNotifier: BACKGROUND_TASK_DONE subscriber for web-originated voice work

[POS]
Server business layer. Closes the WebUI loop when BtwTaskNotifier skips web chats.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone

from app.core.channel_bridge.btw_notifier import _format_notification
from app.core.channel_bridge.persistent_background import BACKGROUND_SOURCE_VOICE
from app.services.chat.chat_service import ChatService
from app.services.event.app_event_bus import (
    AppEvent,
    AppEventType,
    ServerEventBus,
    get_event_bus,
)

logger = logging.getLogger(__name__)

_MAX_DELIVERED_IDS = 512


class WebuiVoiceWorkNotifier:
    """Append voice background task results to the originating WebUI chat."""

    def __init__(self, event_bus: ServerEventBus) -> None:
        self._bus = event_bus
        self._queue: asyncio.Queue[AppEvent] | None = None
        self._task: asyncio.Task[None] | None = None
        self._delivered: set[str] = set()
        self._delivered_order: deque[str] = deque()

    async def start(self) -> None:
        self._queue = self._bus.subscribe()
        self._task = asyncio.create_task(self._loop(), name="webui-voice-work-notifier")
        logger.info("WebuiVoiceWorkNotifier started")

    async def stop(self) -> None:
        if self._queue:
            try:
                self._bus.unsubscribe(self._queue)
            except Exception as exc:
                logger.warning("Failed to unsubscribe WebuiVoiceWorkNotifier: %s", exc)
            self._queue = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("WebuiVoiceWorkNotifier task error during stop: %s", exc)
            self._task = None
        self._delivered.clear()
        self._delivered_order.clear()
        logger.info("WebuiVoiceWorkNotifier stopped")

    async def _loop(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            if event.event_type != AppEventType.BACKGROUND_TASK_DONE:
                continue
            await self._deliver(event.data)

    def _remember_delivery(self, task_id: str) -> None:
        if task_id in self._delivered:
            return
        self._delivered.add(task_id)
        self._delivered_order.append(task_id)
        while len(self._delivered_order) > _MAX_DELIVERED_IDS:
            old = self._delivered_order.popleft()
            self._delivered.discard(old)

    async def _deliver(self, data: dict[str, object]) -> None:
        if str(data.get("background_source", "")) != BACKGROUND_SOURCE_VOICE:
            return

        source_chat_id = str(data.get("source_chat_id", "") or data.get("chat_id", "")).strip()
        if not source_chat_id:
            return

        task_id = str(data.get("task_id", ""))
        if not task_id or task_id in self._delivered:
            return

        chat = await ChatService.get_chat_by_id(source_chat_id)
        if chat is None or chat.source != "web":
            return

        status = str(data.get("status", ""))
        title = str(data.get("title", ""))
        result = str(data.get("result", ""))
        locale = str(data.get("locale", "en"))
        content = _format_notification(status, title, result, locale)
        title_line = content.split("\n", maxsplit=1)[0][:120]
        message_id = f"voice_bg_done_{task_id}"
        sent_at = datetime.now(tz=timezone.utc)

        try:
            await ChatService.append_message(
                chat_id=source_chat_id,
                role="assistant",
                content=content,
                sent_at=sent_at,
                sent_timezone="UTC",
                message_id=message_id,
                extra_data={
                    "voice_background_task": True,
                    "task_id": task_id,
                    "status": status,
                },
            )
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.SYSTEM_NOTIFICATION,
                    data={
                        "title": title_line,
                        "message": content,
                        "meta_data": {
                            "kind": "voice_background_task_done",
                            "chat_id": source_chat_id,
                            "task_id": task_id,
                            "status": status,
                        },
                    },
                )
            )
            self._remember_delivery(task_id)
            logger.info(
                "Voice background task result recorded for web chat=%s task=%s",
                source_chat_id,
                task_id,
            )
        except Exception:
            logger.exception(
                "Failed to deliver voice background result chat=%s task=%s",
                source_chat_id,
                task_id,
            )
