"""Tests for WebuiVoiceWorkNotifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel_bridge.persistent_background import BACKGROUND_SOURCE_VOICE
from app.services.event.app_event_bus import ServerEventBus


def _make_event_bus() -> ServerEventBus:
    return ServerEventBus()


def _voice_done_payload(
    *,
    task_id: str = "task-v1",
    source_chat_id: str = "web-chat-1",
) -> dict[str, object]:
    return {
        "background_source": BACKGROUND_SOURCE_VOICE,
        "source_chat_id": source_chat_id,
        "task_id": task_id,
        "status": "completed",
        "title": "research topic",
        "result": "summary ready",
        "locale": "en",
    }


class TestWebuiVoiceWorkNotifier:
    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        from app.core.channel_bridge.webui_voice_work_notifier import WebuiVoiceWorkNotifier

        bus = _make_event_bus()
        notifier = WebuiVoiceWorkNotifier(bus)

        await notifier.start()
        assert notifier._task is not None
        assert notifier._queue is not None

        await notifier.stop()
        assert notifier._task is None
        assert notifier._queue is None

    @pytest.mark.asyncio
    async def test_deliver_skips_non_voice_source(self) -> None:
        from app.core.channel_bridge.webui_voice_work_notifier import WebuiVoiceWorkNotifier

        bus = _make_event_bus()
        notifier = WebuiVoiceWorkNotifier(bus)

        with patch(
            "app.core.channel_bridge.webui_voice_work_notifier.ChatService.get_chat_by_id",
            new=AsyncMock(),
        ) as get_chat:
            await notifier._deliver({"background_source": "btw", "task_id": "t1"})
            get_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_deliver_skips_non_web_chat(self) -> None:
        from app.core.channel_bridge.webui_voice_work_notifier import WebuiVoiceWorkNotifier

        bus = _make_event_bus()
        notifier = WebuiVoiceWorkNotifier(bus)

        chat = MagicMock()
        chat.source = "discord"

        with patch(
            "app.core.channel_bridge.webui_voice_work_notifier.ChatService.get_chat_by_id",
            new=AsyncMock(return_value=chat),
        ):
            with patch(
                "app.core.channel_bridge.webui_voice_work_notifier.ChatService.append_message",
                new=AsyncMock(),
            ) as append_message:
                await notifier._deliver(_voice_done_payload())
                append_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_deliver_appends_web_chat_and_publishes_sse(self) -> None:
        from app.core.channel_bridge.webui_voice_work_notifier import WebuiVoiceWorkNotifier

        bus = _make_event_bus()
        notifier = WebuiVoiceWorkNotifier(bus)

        chat = MagicMock()
        chat.source = "web"
        append_message = AsyncMock()
        publish = MagicMock()

        with (
            patch(
                "app.core.channel_bridge.webui_voice_work_notifier.ChatService.get_chat_by_id",
                new=AsyncMock(return_value=chat),
            ),
            patch(
                "app.core.channel_bridge.webui_voice_work_notifier.ChatService.append_message",
                new=append_message,
            ),
            patch(
                "app.core.channel_bridge.webui_voice_work_notifier.get_event_bus",
                return_value=MagicMock(publish=publish),
            ),
            patch(
                "app.core.channel_bridge.webui_voice_work_notifier._format_notification",
                return_value="Title line\nBody text",
            ),
        ):
            await notifier._deliver(_voice_done_payload())

        append_message.assert_called_once()
        kwargs = append_message.call_args.kwargs
        assert kwargs["chat_id"] == "web-chat-1"
        assert kwargs["message_id"] == "voice_bg_done_task-v1"
        assert kwargs["extra_data"]["voice_background_task"] is True

        publish.assert_called_once()
        meta = publish.call_args[0][0].data["meta_data"]
        assert meta["kind"] == "voice_background_task_done"
        assert meta["chat_id"] == "web-chat-1"
        assert "task-v1" in notifier._delivered

    @pytest.mark.asyncio
    async def test_deliver_dedupes_same_task_id(self) -> None:
        from app.core.channel_bridge.webui_voice_work_notifier import WebuiVoiceWorkNotifier

        bus = _make_event_bus()
        notifier = WebuiVoiceWorkNotifier(bus)

        chat = MagicMock()
        chat.source = "web"
        append_message = AsyncMock()

        with (
            patch(
                "app.core.channel_bridge.webui_voice_work_notifier.ChatService.get_chat_by_id",
                new=AsyncMock(return_value=chat),
            ),
            patch(
                "app.core.channel_bridge.webui_voice_work_notifier.ChatService.append_message",
                new=append_message,
            ),
            patch(
                "app.core.channel_bridge.webui_voice_work_notifier.get_event_bus",
                return_value=MagicMock(publish=MagicMock()),
            ),
            patch(
                "app.core.channel_bridge.webui_voice_work_notifier._format_notification",
                return_value="Title\nBody",
            ),
        ):
            payload = _voice_done_payload()
            await notifier._deliver(payload)
            await notifier._deliver(payload)

        append_message.assert_called_once()
