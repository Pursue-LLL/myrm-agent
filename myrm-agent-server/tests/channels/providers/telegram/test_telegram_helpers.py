"""Telegram helpers: the inline keyboard builder and media attachment sending."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.telegram.api import TelegramClient
from app.channels.providers.telegram.helpers import (
    build_inline_keyboard,
    send_media_attachment,
)
from app.channels.types import (
    MediaAttachment,
    MediaType,
    OutboundMessage,
)
from app.channels.types.components import (
    ActionButton,
    SelectMenu,
    SelectOption,
)


def _keyboard_rows(msg: OutboundMessage) -> list[list[dict[str, str]]]:
    keyboard = build_inline_keyboard(msg)
    assert keyboard is not None
    return cast("list[list[dict[str, str]]]", keyboard["inline_keyboard"])


class TestBuildInlineKeyboard:
    def test_no_elements(self) -> None:
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
        )
        assert build_inline_keyboard(msg) is None

    def test_quick_replies(self) -> None:
        from app.channels.types import QuickReply

        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
            quick_replies=(QuickReply(label="Yes", text="yes"), QuickReply(label="No", text="no")),
        )
        assert len(_keyboard_rows(msg)) == 2

    def test_action_button_url(self) -> None:
        btn = ActionButton(action_id="a1", label="Visit", url="https://example.com")
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
            components=((btn,),),
        )
        rows = _keyboard_rows(msg)
        assert rows[0][0]["url"] == "https://example.com"

    def test_action_button_callback(self) -> None:
        btn = ActionButton(action_id="a1", label="Click")
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
            components=((btn,),),
        )
        rows = _keyboard_rows(msg)
        assert rows[0][0]["callback_data"].startswith("act:")

    def test_select_menu(self) -> None:
        menu = SelectMenu(
            action_id="s1",
            placeholder="Choose",
            options=(
                SelectOption(label="A", value="a"),
                SelectOption(label="B", value="b"),
            ),
        )
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
            components=((menu,),),
        )
        rows = _keyboard_rows(msg)
        assert len(rows[0]) == 2


class TestSendMediaAttachment:
    @pytest.mark.asyncio
    async def test_send_image_url(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_photo = AsyncMock()
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.com/a.png")
        await send_media_attachment(client, "123", att, None)
        client.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_document_fallback(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_document = AsyncMock()
        att = MediaAttachment(media_type=MediaType.DOCUMENT, url="https://example.com/file.pdf")
        await send_media_attachment(client, "123", att, "42")
        client.send_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_source_is_a_permanent_failure(self) -> None:
        client = MagicMock(spec=TelegramClient)
        att = MediaAttachment(media_type=MediaType.IMAGE)
        with pytest.raises(ChannelSendError) as exc_info:
            await send_media_attachment(client, "123", att, None)
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_missing_local_file_is_a_permanent_failure(self, tmp_path: Path) -> None:
        client = MagicMock(spec=TelegramClient)
        att = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "gone.pdf"))
        with pytest.raises(ChannelSendError) as exc_info:
            await send_media_attachment(client, "123", att, None)
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_empty_local_file_is_a_permanent_failure(self, tmp_path: Path) -> None:
        client = MagicMock(spec=TelegramClient)
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        with pytest.raises(ChannelSendError) as exc_info:
            await send_media_attachment(client, "123", MediaAttachment(media_type=MediaType.DOCUMENT, path=str(empty)), None)
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_with_filename(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_document = AsyncMock()
        att = MediaAttachment(
            media_type=MediaType.DOCUMENT,
            url="https://example.com/f.pdf",
            filename="report.pdf",
        )
        await send_media_attachment(client, "123", att, None)
        call_kwargs = client.send_document.call_args
        assert call_kwargs[1].get("filename") == "report.pdf"

    @pytest.mark.asyncio
    async def test_send_video(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_video = AsyncMock()
        att = MediaAttachment(media_type=MediaType.VIDEO, url="https://example.com/v.mp4")
        await send_media_attachment(client, "123", att, None)
        client.send_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_audio(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_voice = AsyncMock()
        att = MediaAttachment(media_type=MediaType.AUDIO, url="https://example.com/a.ogg")
        await send_media_attachment(client, "123", att, None)
        client.send_voice.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_image_from_path(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_photo = AsyncMock()
        att = MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/photo.jpg")
        with patch(
            "app.channels.providers.telegram.helpers.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=b"fake-jpeg",
        ) as mock_to_thread:
            await send_media_attachment(client, "123", att, None)
            mock_to_thread.assert_awaited_once()
        client.send_photo.assert_called_once()
        assert client.send_photo.call_args[0][1] == b"fake-jpeg"

    @pytest.mark.asyncio
    async def test_send_image_url_preferred_over_path(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_photo = AsyncMock()
        att = MediaAttachment(
            media_type=MediaType.IMAGE,
            url="https://img.com/a.png",
            path="/tmp/photo.jpg",
        )
        with patch(
            "app.channels.providers.telegram.helpers.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread:
            await send_media_attachment(client, "123", att, None)
            mock_to_thread.assert_not_awaited()
        client.send_photo.assert_called_once()
        assert client.send_photo.call_args[0][1] == "https://img.com/a.png"
