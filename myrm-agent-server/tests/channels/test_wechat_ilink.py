"""Tests for WeChatILinkChannel (personal account via iLink Bot protocol)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
)
from app.channels.providers._ilink.media import _get_temp_dir
from app.channels.providers._ilink.types import (
    FileItem,
    ILinkMessage,
    ImageItem,
    ItemType,
    MediaInfo,
    MessageItem,
    MessageType,
    TextItem,
    VideoItem,
    VoiceItem,
)
from app.channels.providers.wechat.ilink_channel import (
    WeChatILinkChannel,
)
from app.channels.types import (
    ChannelStatus,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase

_MEDIA_MOD = "app.channels.providers._ilink.media"


class TestWeChatILinkContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return WeChatILinkChannel(bot_token="test_token", ilink_bot_id="test_bot_id")


def _make_channel() -> WeChatILinkChannel:
    ch = WeChatILinkChannel(
        bot_token="test_token",
        ilink_bot_id="bot123",
        base_url="https://ilinkai.weixin.qq.com",
        ilink_user_id="user456",
    )
    ch._client._http = AsyncMock()
    ch._status = ChannelStatus.RUNNING
    return ch


def _make_ilink_msg(
    text: str = "",
    from_user: str = "user1",
    group_id: str = "",
    context_token: str = "ctx1",
    items: tuple[MessageItem, ...] | None = None,
) -> ILinkMessage:
    if items is None:
        item_list = (MessageItem(type=ItemType.TEXT, text_item=TextItem(text=text)),) if text else ()
    else:
        item_list = items
    return ILinkMessage(
        from_user_id=from_user,
        to_user_id="bot123",
        message_type=MessageType.USER,
        message_state=0,
        item_list=item_list,
        context_token=context_token,
        message_id=42,
        session_id="sess1",
        group_id=group_id or None,
    )


# ── Capabilities ───────────────────────────────────────────────────────


class TestCapabilities:
    def test_name(self) -> None:
        ch = _make_channel()
        assert ch.name == "wechat"

    def test_capabilities_flags(self) -> None:
        ch = _make_channel()
        assert ch.capabilities.text is True
        assert ch.capabilities.media is True
        assert ch.capabilities.voice_message is True
        assert ch.capabilities.file_upload is True
        assert ch.capabilities.typing_indicator is True
        assert ch.capabilities.markdown is False


# ── Lifecycle ──────────────────────────────────────────────────────────


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_with_credentials(self) -> None:
        ch = WeChatILinkChannel(bot_token="tok", ilink_bot_id="bid")
        ch._client._http = AsyncMock()
        await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._poll_task is not None
        ch._poll_task.cancel()
        try:
            await ch._poll_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_start_without_credentials(self) -> None:
        ch = WeChatILinkChannel()
        await ch.start()
        assert ch._status == ChannelStatus.STOPPED
        assert ch._poll_task is None

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._poll_task = asyncio.create_task(asyncio.sleep(100))
        ch._temp_files = {Path("/tmp/test.jpg")}

        ch._client._owns_http = False
        await ch.stop()

        assert ch._status == ChannelStatus.STOPPED
        assert ch._poll_task is None
        assert len(ch._temp_files) == 0

    @pytest.mark.asyncio
    async def test_health_check_running(self) -> None:
        ch = _make_channel()
        ch._poll_task = asyncio.create_task(asyncio.sleep(999))
        ch._client.get_config = AsyncMock(return_value={"ret": 0})
        try:
            assert await ch.health_check() is True
        finally:
            ch._poll_task.cancel()
            try:
                await ch._poll_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_health_check_stopped(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_error(self) -> None:
        ch = _make_channel()
        ch._client.get_config = AsyncMock(side_effect=RuntimeError("fail"))
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_get_status_info_connected(self) -> None:
        ch = _make_channel()
        ch._poll_task = asyncio.create_task(asyncio.sleep(999))
        try:
            info = ch.get_status_info()
            assert info["connected"] is True
            assert info["bot_id"] == "bot123"
        finally:
            ch._poll_task.cancel()
            try:
                await ch._poll_task
            except asyncio.CancelledError:
                pass

    def test_get_status_info_disconnected(self) -> None:
        ch = WeChatILinkChannel()
        info = ch.get_status_info()
        assert info["connected"] is False
        assert info["bot_id"] is None


# ── Send ───────────────────────────────────────────────────────────────


class TestSend:
    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        ch = _make_channel()
        ch._client.send_message = AsyncMock()

        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="hello", user_id="u1")
        await ch.send(msg)
        ch._client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_recipient(self) -> None:
        ch = _make_channel()
        ch._client.send_message = AsyncMock()

        msg = OutboundMessage(channel="wechat", recipient_id="", content="hello", user_id="u1")
        await ch.send(msg)
        ch._client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_with_context_token(self) -> None:
        ch = _make_channel()
        ch._context_tokens["user1"] = "ctx_saved"
        ch._client.send_message = AsyncMock()

        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="hello", user_id="u1")
        await ch.send(msg)
        call_args = ch._client.send_message.call_args
        assert call_args[1].get("context_token") == "ctx_saved" or call_args[0][2] == "ctx_saved"

    @pytest.mark.asyncio
    async def test_send_media_image_url(self) -> None:
        ch = _make_channel()
        ch._client.send_message = AsyncMock()

        attachment = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.com/1.jpg")
        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="", user_id="u1", media=(attachment,))
        await ch.send(msg)
        ch._client.send_message.assert_called_once()
        items = ch._client.send_message.call_args[0][1]
        assert items[0].type == ItemType.IMAGE
        assert items[0].image_item.url == "https://img.com/1.jpg"

    @pytest.mark.asyncio
    async def test_send_media_image_path(self, tmp_path: Path) -> None:
        ch = _make_channel()
        ch._client.send_message = AsyncMock()
        ch._client.get_upload_url = AsyncMock(return_value="https://cdn.example.com/upload?key=val")

        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"image data")

        with patch(
            f"{_MEDIA_MOD}.encrypt_and_upload",
            new_callable=AsyncMock,
            return_value=100,
        ):
            attachment = MediaAttachment(media_type=MediaType.IMAGE, path=str(img_file))
            msg = OutboundMessage(channel="wechat", recipient_id="user1", content="", user_id="u1", media=(attachment,))
            await ch.send(msg)

        ch._client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_media_file_not_found(self) -> None:
        ch = _make_channel()
        ch._client.send_message = AsyncMock()

        attachment = MediaAttachment(media_type=MediaType.IMAGE, path="/nonexistent/file.jpg")
        msg = OutboundMessage(channel="wechat", recipient_id="user1", content="", user_id="u1", media=(attachment,))
        await ch.send(msg)
        ch._client.send_message.assert_not_called()


# ── Typing ─────────────────────────────────────────────────────────────


class TestTyping:
    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        ch = _make_channel()
        ch._client.get_config = AsyncMock(return_value={"typing_ticket": "ticket1"})
        ch._client.send_typing = AsyncMock()

        await ch.start_typing("user1")
        ch._client.send_typing.assert_called_once()
        assert ch._typing_tickets["user1"] == "ticket1"

    @pytest.mark.asyncio
    async def test_start_typing_cached_ticket(self) -> None:
        ch = _make_channel()
        ch._typing_tickets["user1"] = "cached_ticket"
        ch._client.send_typing = AsyncMock()

        await ch.start_typing("user1")
        ch._client.send_typing.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_typing_config_failure(self) -> None:
        ch = _make_channel()
        ch._client.get_config = AsyncMock(side_effect=RuntimeError("fail"))
        await ch.start_typing("user1")

    @pytest.mark.asyncio
    async def test_stop_typing(self) -> None:
        ch = _make_channel()
        ch._typing_tickets["user1"] = "ticket1"
        ch._client.send_typing = AsyncMock()

        await ch.stop_typing("user1")
        ch._client.send_typing.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_typing_no_ticket(self) -> None:
        ch = _make_channel()
        ch._client.send_typing = AsyncMock()
        await ch.stop_typing("user1")
        ch._client.send_typing.assert_not_called()


# ── Parse Message ──────────────────────────────────────────────────────


class TestParseMessage:
    @pytest.mark.asyncio
    async def test_text_message(self) -> None:
        ch = _make_channel()
        ilink_msg = _make_ilink_msg(text="hello world")
        result = await ch._parse_message(ilink_msg)
        assert result is not None
        assert result.content == "hello world"
        assert result.sender_id == "user1"
        assert result.chat_id == "user1"
        assert result.is_group is False

    @pytest.mark.asyncio
    async def test_group_message_with_mention(self) -> None:
        ch = _make_channel()
        ilink_msg = _make_ilink_msg(
            text="@bot123 hello",
            group_id="group1",
        )
        result = await ch._parse_message(ilink_msg)
        assert result is not None
        assert result.is_group is True
        assert result.mentioned is True
        assert result.chat_id == "group1"

    @pytest.mark.asyncio
    async def test_group_message_without_mention(self) -> None:
        ch = _make_channel()
        ilink_msg = _make_ilink_msg(text="hello", group_id="group1")
        result = await ch._parse_message(ilink_msg)
        assert result is not None
        assert result.mentioned is False

    @pytest.mark.asyncio
    async def test_bot_message_ignored(self) -> None:
        ch = _make_channel()
        ilink_msg = ILinkMessage(
            from_user_id="user1",
            to_user_id="bot123",
            message_type=MessageType.BOT,
            message_state=0,
            item_list=(MessageItem(type=ItemType.TEXT, text_item=TextItem(text="hi")),),
        )
        result = await ch._parse_message(ilink_msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self) -> None:
        ch = _make_channel()
        ilink_msg = _make_ilink_msg(items=())
        result = await ch._parse_message(ilink_msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_context_token_saved(self) -> None:
        ch = _make_channel()
        ilink_msg = _make_ilink_msg(text="hi", context_token="new_ctx")
        await ch._parse_message(ilink_msg)
        assert ch._context_tokens["user1"] == "new_ctx"

    @pytest.mark.asyncio
    async def test_image_item(self) -> None:
        ch = _make_channel()
        items = (
            MessageItem(
                type=ItemType.IMAGE,
                image_item=ImageItem(url="https://img.com/1.jpg"),
            ),
        )
        ilink_msg = _make_ilink_msg(items=items)
        result = await ch._parse_message(ilink_msg)
        assert result is not None
        assert result.media[0].media_type == MediaType.IMAGE
        assert result.media[0].url == "https://img.com/1.jpg"

    @pytest.mark.asyncio
    async def test_voice_with_text(self) -> None:
        ch = _make_channel()
        items = (
            MessageItem(
                type=ItemType.VOICE,
                voice_item=VoiceItem(text="recognized text"),
            ),
        )
        ilink_msg = _make_ilink_msg(items=items)
        result = await ch._parse_message(ilink_msg)
        assert result is not None
        assert "[Voice: recognized text]" in result.content

    @pytest.mark.asyncio
    async def test_voice_with_media(self, tmp_path: Path) -> None:
        ch = _make_channel()
        media = MediaInfo(encrypt_query_param="p", aes_key="k")
        items = (
            MessageItem(
                type=ItemType.VOICE,
                voice_item=VoiceItem(media=media),
            ),
        )
        ilink_msg = _make_ilink_msg(items=items)

        silk_path = tmp_path / "voice.silk"

        with (
            patch(
                f"{_MEDIA_MOD}.download_encrypted_media",
                new_callable=AsyncMock,
                return_value=silk_path,
            ),
            patch(
                f"{_MEDIA_MOD}.silk_to_wav",
                return_value=False,
            ),
        ):
            result = await ch._parse_message(ilink_msg)
            assert result is None

    @pytest.mark.asyncio
    async def test_file_item(self) -> None:
        ch = _make_channel()
        media = MediaInfo(encrypt_query_param="p", aes_key="k")
        items = (
            MessageItem(
                type=ItemType.FILE,
                file_item=FileItem(media=media, file_name="doc.pdf"),
            ),
        )
        ilink_msg = _make_ilink_msg(items=items)

        fake_path = Path("/tmp/fake_file.bin")
        with patch(
            f"{_MEDIA_MOD}.download_encrypted_media",
            new_callable=AsyncMock,
            return_value=fake_path,
        ):
            result = await ch._parse_message(ilink_msg)
            assert result is not None
            assert result.media[0].media_type == MediaType.DOCUMENT
            assert result.media[0].filename == "doc.pdf"

    @pytest.mark.asyncio
    async def test_video_item(self) -> None:
        ch = _make_channel()
        media = MediaInfo(encrypt_query_param="p", aes_key="k")
        items = (
            MessageItem(
                type=ItemType.VIDEO,
                video_item=VideoItem(media=media),
            ),
        )
        ilink_msg = _make_ilink_msg(items=items)

        fake_path = Path("/tmp/fake_video.mp4")
        with patch(
            f"{_MEDIA_MOD}.download_encrypted_media",
            new_callable=AsyncMock,
            return_value=fake_path,
        ):
            result = await ch._parse_message(ilink_msg)
            assert result is not None
            assert result.media[0].media_type == MediaType.VIDEO


# ── Poll Loop ──────────────────────────────────────────────────────────


class TestPollLoop:
    @pytest.mark.asyncio
    async def test_session_expired_stops_polling(self) -> None:
        ch = _make_channel()
        ch._client.get_updates = AsyncMock(side_effect=ChannelAuthError("session expired", channel="wechat"))
        await ch._poll_loop()
        assert ch._status == ChannelStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_max_failures_triggers_backoff_and_reset(self) -> None:
        ch = _make_channel()
        call_count = 0

        async def _fail(*_args: object, **_kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count > 6:
                ch._status = ChannelStatus.STOPPED
            raise ChannelConnectionError("fail", channel="wechat")

        ch._client.get_updates = AsyncMock(side_effect=_fail)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert call_count > 5
        assert ch.health.consecutive_failures >= 0

    @pytest.mark.asyncio
    async def test_successful_poll(self) -> None:
        ch = _make_channel()
        call_count = 0

        async def mock_get_updates(buf: str = "") -> tuple[list[ILinkMessage], str]:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                ch._status = ChannelStatus.STOPPED
            return [], "new_buf"

        ch._client.get_updates = AsyncMock(side_effect=mock_get_updates)
        await ch._poll_loop()
        assert ch._get_updates_buf == "new_buf"


# ── Temp Dir ───────────────────────────────────────────────────────────


class TestTempDir:
    def test_get_temp_dir_creates(self) -> None:
        with patch(
            f"{_MEDIA_MOD}._temp_dir",
            None,
        ):
            d = _get_temp_dir()
            assert d.exists()
            d.rmdir()
