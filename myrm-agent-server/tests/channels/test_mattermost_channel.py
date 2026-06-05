"""MattermostChannel contract compliance + outbound / inbound / lifecycle tests."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.mattermost import MattermostChannel
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase


class TestMattermostChannel(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return MattermostChannel(
            server_url="https://mm.example.com",
            access_token="test-bot-token",
        )


def _make_channel() -> MattermostChannel:
    ch = MattermostChannel(server_url="https://mm.example.com", access_token="test-token")
    ch._bot_id = "bot_user_id"
    ch._api._bot_user_id = "bot_user_id"
    return ch


def _post_response(post_id: str = "post_1") -> dict[str, object]:
    return {"id": post_id, "channel_id": "ch_1", "message": "ok"}


class TestMattermostOutbound:
    """Tests for send / edit / delete / react outbound methods."""

    @pytest.mark.asyncio
    async def test_send_basic_message(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value=_post_response("p1")):
            msg = OutboundMessage(
                channel="mattermost",
                recipient_id="ch_1",
                content="Hello",
                user_id="u1",
            )
            result = await ch.send(msg)
        assert result == "p1"
        assert not ch.health.last_error

    @pytest.mark.asyncio
    async def test_send_with_thread_id(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value=_post_response()) as mock_post:
            msg = OutboundMessage(
                channel="mattermost",
                recipient_id="ch_1",
                content="Reply",
                user_id="u1",
                metadata={"thread_id": "root_123"},
            )
            await ch.send(msg)
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs.get("root_id") == "root_123"

    @pytest.mark.asyncio
    async def test_send_with_reply_to_id(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value=_post_response()) as mock_post:
            msg = OutboundMessage(
                channel="mattermost",
                recipient_id="ch_1",
                content="Reply",
                user_id="u1",
                reply_to_id="parent_post",
            )
            await ch.send(msg)
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs.get("root_id") == "parent_post"

    @pytest.mark.asyncio
    async def test_send_empty_content_returns_none(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="mattermost",
            recipient_id="ch_1",
            content="",
            user_id="u1",
        )
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_no_recipient_returns_none(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="mattermost",
            recipient_id="",
            content="Hello",
            user_id="u1",
        )
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_http_error_raises_channel_send_error(self) -> None:
        ch = _make_channel()
        request = httpx.Request("POST", "https://mm.example.com/api/v4/posts")
        response = httpx.Response(500, request=request)
        exc = httpx.HTTPStatusError("Server Error", request=request, response=response)
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, side_effect=exc):
            msg = OutboundMessage(
                channel="mattermost",
                recipient_id="ch_1",
                content="Hello",
                user_id="u1",
            )
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is True
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_send_429_retriable(self) -> None:
        ch = _make_channel()
        request = httpx.Request("POST", "https://mm.example.com/api/v4/posts")
        response = httpx.Response(429, request=request)
        exc = httpx.HTTPStatusError("Rate Limited", request=request, response=response)
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, side_effect=exc):
            msg = OutboundMessage(
                channel="mattermost",
                recipient_id="ch_1",
                content="Hello",
                user_id="u1",
            )
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is True

    @pytest.mark.asyncio
    async def test_send_403_not_retriable(self) -> None:
        ch = _make_channel()
        request = httpx.Request("POST", "https://mm.example.com/api/v4/posts")
        response = httpx.Response(403, request=request)
        exc = httpx.HTTPStatusError("Forbidden", request=request, response=response)
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, side_effect=exc):
            msg = OutboundMessage(
                channel="mattermost",
                recipient_id="ch_1",
                content="Hello",
                user_id="u1",
            )
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_generic_error_raises_channel_send_error(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, side_effect=RuntimeError("conn")):
            msg = OutboundMessage(
                channel="mattermost",
                recipient_id="ch_1",
                content="Hello",
                user_id="u1",
            )
            with pytest.raises(ChannelSendError):
                await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_with_media(self) -> None:
        ch = _make_channel()
        media = (MediaAttachment(media_type="image", url="https://img.com/pic.png", filename="pic.png"),)

        with (
            patch(
                "app.channels.media.downloader.MediaDownloader.download",
                new_callable=AsyncMock,
            ) as mock_download,
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, return_value="file_1"),
            patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value=_post_response()) as mock_post,
        ):
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.data = b"imagedata"
            mock_download.return_value = mock_result

            msg = OutboundMessage(
                channel="mattermost",
                recipient_id="ch_1",
                content="See pic",
                user_id="u1",
                media=media,
            )
            await ch.send(msg)
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs.get("file_ids") == ["file_1"]

    @pytest.mark.asyncio
    async def test_send_placeholder(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value=_post_response("ph_1")):
            result = await ch.send_placeholder("ch_1", "Thinking...")
        assert result == "ph_1"

    @pytest.mark.asyncio
    async def test_send_placeholder_with_thread(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value=_post_response("ph_2")) as mock:
            result = await ch.send_placeholder("ch_1", "...", thread_id="root_1")
        assert result == "ph_2"
        assert mock.call_args.kwargs.get("root_id") == "root_1"

    @pytest.mark.asyncio
    async def test_send_placeholder_failure(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, side_effect=Exception("err")):
            result = await ch.send_placeholder("ch_1", "...")
        assert result is None

    @pytest.mark.asyncio
    async def test_edit_message(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "update_post", new_callable=AsyncMock) as mock:
            await ch.edit_message("ch_1", "msg_1", "Updated text")
        mock.assert_called_once_with("msg_1", "Updated text")

    @pytest.mark.asyncio
    async def test_edit_message_failure(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "update_post", new_callable=AsyncMock, side_effect=Exception("err")):
            await ch.edit_message("ch_1", "msg_1", "Updated")

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "delete_post", new_callable=AsyncMock) as mock:
            await ch.delete_message("ch_1", "msg_1")
        mock.assert_called_once_with("msg_1")

    @pytest.mark.asyncio
    async def test_delete_message_failure(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "delete_post", new_callable=AsyncMock, side_effect=Exception("err")):
            await ch.delete_message("ch_1", "msg_1")

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "add_reaction", new_callable=AsyncMock) as mock:
            await ch.react_to_message("ch_1", "msg_1", ":thumbsup:")
        mock.assert_called_once_with("bot_user_id", "msg_1", "thumbsup")

    @pytest.mark.asyncio
    async def test_react_empty_emoji_noop(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "add_reaction", new_callable=AsyncMock) as mock:
            await ch.react_to_message("ch_1", "msg_1", "")
        mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_react_no_bot_id_noop(self) -> None:
        ch = _make_channel()
        ch._bot_id = ""
        with patch.object(ch._api, "add_reaction", new_callable=AsyncMock) as mock:
            await ch.react_to_message("ch_1", "msg_1", "wave")
        mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_react_failure(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "add_reaction", new_callable=AsyncMock, side_effect=Exception("err")):
            await ch.react_to_message("ch_1", "msg_1", "wave")


class TestMattermostInbound:
    """Tests for WebSocket inbound message handling."""

    @pytest.mark.asyncio
    async def test_handle_posted_emits_inbound(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "user_1",
                "message": "Hello bot",
                "channel_id": "ch_1",
                "id": "post_1",
                "root_id": "",
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {
                "post": post_data,
                "channel_type": "O",
                "sender_name": "testuser",
                "mentions": json.dumps(["bot_user_id"]),
            },
        }
        await ch._handle_posted(event)
        assert len(received) == 1
        assert received[0].content == "Hello bot"
        assert received[0].sender_id == "user_1"
        assert received[0].is_group is True
        assert received[0].mentioned is True
        assert received[0].sender_name == "testuser"

    @pytest.mark.asyncio
    async def test_handle_posted_dm_not_group(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "user_1",
                "message": "DM msg",
                "channel_id": "ch_dm",
                "id": "p2",
                "root_id": "",
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {"post": post_data, "channel_type": "D", "sender_name": "user"},
        }
        await ch._handle_posted(event)
        assert len(received) == 1
        assert received[0].is_group is False
        assert received[0].mentioned is True

    @pytest.mark.asyncio
    async def test_handle_posted_thread_reply(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "user_1",
                "message": "thread reply",
                "channel_id": "ch_1",
                "id": "p3",
                "root_id": "root_post",
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {
                "post": post_data,
                "channel_type": "O",
                "sender_name": "user",
                "mentions": json.dumps(["bot_user_id"]),
            },
        }
        await ch._handle_posted(event)
        assert len(received) == 1
        assert received[0].thread_id == "root_post"

    @pytest.mark.asyncio
    async def test_handle_posted_filters_bot_self(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "bot_user_id",
                "message": "bot msg",
                "channel_id": "ch_1",
                "id": "p4",
                "root_id": "",
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {"post": post_data, "channel_type": "O"},
        }
        await ch._handle_posted(event)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_handle_posted_empty_message_ignored(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "user_1",
                "message": "  ",
                "channel_id": "ch_1",
                "id": "p5",
                "root_id": "",
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {"post": post_data, "channel_type": "O"},
        }
        await ch._handle_posted(event)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_handle_posted_invalid_json_ignored(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event: dict[str, object] = {
            "event": "posted",
            "data": {"post": "not-valid-json{{{", "channel_type": "O"},
        }
        await ch._handle_posted(event)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_handle_posted_no_data_ignored(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        await ch._handle_posted({"event": "posted"})
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_group_not_mentioned_filtered(self) -> None:
        """Group message without @bot is filtered by AllowPolicy (MENTION_ONLY)."""
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "user_1",
                "message": "general chat",
                "channel_id": "ch_1",
                "id": "p_no_mention",
                "root_id": "",
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {"post": post_data, "channel_type": "O", "sender_name": "user"},
        }
        await ch._handle_posted(event)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_group_mentioned_other_user_filtered(self) -> None:
        """Group message mentioning another user (not bot) is filtered."""
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "user_1",
                "message": "@other hello",
                "channel_id": "ch_1",
                "id": "p_other",
                "root_id": "",
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {
                "post": post_data,
                "channel_type": "O",
                "mentions": json.dumps(["other_user_id"]),
            },
        }
        await ch._handle_posted(event)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_bot_mention_stripped(self) -> None:
        """@botname is removed from message text."""
        ch = _make_channel()
        ch._bot_name = "mybot"
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "user_1",
                "message": "@mybot what is 2+2?",
                "channel_id": "ch_1",
                "id": "p_strip",
                "root_id": "",
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {
                "post": post_data,
                "channel_type": "O",
                "mentions": json.dumps(["bot_user_id"]),
            },
        }
        await ch._handle_posted(event)
        assert len(received) == 1
        assert received[0].content == "what is 2+2?"

    @pytest.mark.asyncio
    async def test_inbound_media_from_file_ids(self) -> None:
        """Post with file_ids produces MediaAttachment entries."""
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "user_1",
                "message": "check this file",
                "channel_id": "ch_1",
                "id": "p_media",
                "root_id": "",
                "file_ids": ["fid_a", "fid_b"],
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {"post": post_data, "channel_type": "D"},
        }
        await ch._handle_posted(event)
        assert len(received) == 1
        assert len(received[0].media) == 2
        assert received[0].media[0].url == "https://mm.example.com/api/v4/files/fid_a"
        assert received[0].media[0].media_type == MediaType.DOCUMENT
        assert received[0].media[1].url == "https://mm.example.com/api/v4/files/fid_b"

    @pytest.mark.asyncio
    async def test_inbound_no_file_ids(self) -> None:
        """Post without file_ids has empty media tuple."""
        ch = _make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        post_data = json.dumps(
            {
                "user_id": "user_1",
                "message": "text only",
                "channel_id": "ch_1",
                "id": "p_nomedia",
                "root_id": "",
            }
        )
        event: dict[str, object] = {
            "event": "posted",
            "data": {"post": post_data, "channel_type": "D"},
        }
        await ch._handle_posted(event)
        assert len(received) == 1
        assert received[0].media == ()


class TestMattermostReactionInbound:
    """Inbound ``reaction_added`` WebSocket event handling.

    Covers the bridge between Mattermost emoji shortcodes and the unified
    Unicode reaction approval vocabulary consumed by ``parse_approval_command``.
    """

    @staticmethod
    def _reaction_event(
        *,
        emoji_name: str,
        user_id: str = "user_1",
        post_id: str = "post_42",
        channel_id: str = "ch_1",
        channel_type: str = "O",
        bot_id: str = "bot_user_id",
    ) -> dict[str, object]:
        reaction = {
            "user_id": user_id,
            "post_id": post_id,
            "emoji_name": emoji_name,
            "channel_id": channel_id,
        }
        return {
            "event": "reaction_added",
            "data": {
                "reaction": json.dumps(reaction),
                "channel_type": channel_type,
                "bot_id": bot_id,
            },
        }

    async def _capture(self, ch: MattermostChannel, event: dict[str, object]) -> list[InboundMessage]:
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        await ch._handle_reaction_added(event)
        return received

    @pytest.mark.asyncio
    async def test_thumbsup_shortcode_maps_to_unicode(self) -> None:
        ch = _make_channel()
        received = await self._capture(ch, self._reaction_event(emoji_name="thumbsup"))
        assert len(received) == 1
        assert received[0].content == "\U0001f44d"
        assert received[0].sender_id == "user_1"
        assert received[0].channel == "mattermost"
        assert received[0].is_group is True
        assert received[0].metadata["reaction"] is True
        assert received[0].metadata["target_message_id"] == "post_42"
        assert received[0].message_id == "post_42"

    @pytest.mark.asyncio
    async def test_plus_one_shortcode_alias(self) -> None:
        ch = _make_channel()
        received = await self._capture(ch, self._reaction_event(emoji_name="+1"))
        assert len(received) == 1
        assert received[0].content == "\U0001f44d"

    @pytest.mark.asyncio
    async def test_infinity_shortcode_maps_to_allow_always(self) -> None:
        ch = _make_channel()
        received = await self._capture(ch, self._reaction_event(emoji_name="infinity"))
        assert len(received) == 1
        assert received[0].content == "\u267e"

    @pytest.mark.asyncio
    async def test_thumbsdown_shortcode_maps_to_deny(self) -> None:
        ch = _make_channel()
        received = await self._capture(ch, self._reaction_event(emoji_name="thumbsdown"))
        assert len(received) == 1
        assert received[0].content == "\U0001f44e"

    @pytest.mark.asyncio
    async def test_dm_channel_marks_not_group(self) -> None:
        ch = _make_channel()
        received = await self._capture(
            ch,
            self._reaction_event(emoji_name="thumbsup", channel_type="D"),
        )
        assert len(received) == 1
        assert received[0].is_group is False

    @pytest.mark.asyncio
    async def test_unknown_emoji_dropped(self) -> None:
        ch = _make_channel()
        received = await self._capture(ch, self._reaction_event(emoji_name="party_blob"))
        assert received == []

    @pytest.mark.asyncio
    async def test_bot_self_reaction_filtered(self) -> None:
        ch = _make_channel()
        received = await self._capture(
            ch,
            self._reaction_event(emoji_name="thumbsup", user_id="bot_user_id"),
        )
        assert received == []

    @pytest.mark.asyncio
    async def test_missing_post_id_dropped(self) -> None:
        ch = _make_channel()
        received = await self._capture(ch, self._reaction_event(emoji_name="thumbsup", post_id=""))
        assert received == []

    @pytest.mark.asyncio
    async def test_invalid_reaction_json_dropped(self) -> None:
        ch = _make_channel()
        event: dict[str, object] = {
            "event": "reaction_added",
            "data": {"reaction": "not-json", "channel_type": "O"},
        }
        received = await self._capture(ch, event)
        assert received == []

    @pytest.mark.asyncio
    async def test_missing_data_dropped(self) -> None:
        ch = _make_channel()
        received = await self._capture(ch, {"event": "reaction_added"})
        assert received == []


class TestMattermostLifecycle:
    """Tests for start / stop / health_check lifecycle."""

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = MattermostChannel(server_url="https://mm.example.com", access_token="tok")
        with patch.object(
            ch._api,
            "get_me",
            new_callable=AsyncMock,
            return_value={"id": "bot_1", "username": "mybot"},
        ):
            ch._api._bot_user_id = "bot_1"
            await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._bot_id == "bot_1"
        assert ch._bot_name == "mybot"
        if ch._ws_task and not ch._ws_task.done():
            ch._ws_task.cancel()
            try:
                await ch._ws_task
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_start_not_configured(self) -> None:
        ch = MattermostChannel(server_url="", access_token="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_auth_failure(self) -> None:
        ch = MattermostChannel(server_url="https://mm.example.com", access_token="bad")
        with patch.object(ch._api, "get_me", new_callable=AsyncMock, side_effect=Exception("auth failed")):
            await ch.start()
        assert ch._status == ChannelStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING

        async def _forever() -> None:
            await asyncio.sleep(999)

        ch._ws_task = asyncio.create_task(_forever())
        with patch.object(ch._api, "close", new_callable=AsyncMock):
            await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_no_ws_task(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._api, "close", new_callable=AsyncMock):
            await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_health_check_ok(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "get_me", new_callable=AsyncMock, return_value={"id": "bot_1"}):
            assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_not_configured(self) -> None:
        ch = MattermostChannel(server_url="", access_token="")
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "get_me", new_callable=AsyncMock, side_effect=Exception("err")):
            assert await ch.health_check() is False
        assert ch.health.last_error == "err"


class TestMattermostListGroups:
    """Tests for list_groups()."""

    @pytest.mark.asyncio
    async def test_list_groups_success(self) -> None:
        ch = _make_channel()
        teams = [{"id": "t1", "name": "Team One"}]
        channels = [
            {"id": "ch_1", "display_name": "General", "type": "O"},
            {"id": "ch_2", "display_name": "Private", "type": "P"},
            {"id": "ch_dm", "display_name": "", "type": "D"},
        ]
        with (
            patch.object(ch._api, "get_teams_for_user", new_callable=AsyncMock, return_value=teams),
            patch.object(ch._api, "get_channels_for_user", new_callable=AsyncMock, return_value=channels),
        ):
            groups = await ch.list_groups()
        assert len(groups) == 2
        assert groups[0].name == "General"
        assert groups[1].name == "Private"

    @pytest.mark.asyncio
    async def test_list_groups_no_bot_id(self) -> None:
        ch = _make_channel()
        ch._api._bot_user_id = ""
        groups = await ch.list_groups()
        assert groups == []

    @pytest.mark.asyncio
    async def test_list_groups_failure(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api, "get_teams_for_user", new_callable=AsyncMock, side_effect=Exception("err")):
            groups = await ch.list_groups()
        assert groups == []


class TestMattermostCollectIssues:
    """Tests for collect_issues()."""

    def test_missing_config(self) -> None:
        ch = MattermostChannel(server_url="", access_token="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "Missing configuration" in issues[0].message

    def test_degraded_status(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.DEGRADED
        issues = ch.collect_issues()
        assert any("degraded" in i.message.lower() for i in issues)

    def test_runtime_error(self) -> None:
        ch = _make_channel()
        ch.health.record_failure("connection timeout")
        issues = ch.collect_issues()
        assert any("connection timeout" in i.message for i in issues)

    def test_healthy_no_issues(self) -> None:
        ch = _make_channel()
        issues = ch.collect_issues()
        assert issues == []


class TestMattermostClient:
    """Unit tests for MattermostClient API methods."""

    @pytest.mark.asyncio
    async def test_get_me(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "bot_1", "username": "bot"}
        mock_resp.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.get_me()
        assert result["id"] == "bot_1"
        assert client._bot_user_id == "bot_1"

    @pytest.mark.asyncio
    async def test_create_post(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "p1", "message": "Hello"}
        mock_resp.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.create_post("ch_1", "Hello", root_id="root_1", file_ids=["f1"])
        assert result["id"] == "p1"
        call_kwargs = mock_http.post.call_args
        body = call_kwargs.kwargs.get("json", {})
        assert body["root_id"] == "root_1"
        assert body["file_ids"] == ["f1"]

    @pytest.mark.asyncio
    async def test_upload_file(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"file_infos": [{"id": "fid_1"}]}
        mock_resp.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.upload_file("ch_1", "test.txt", b"data")
        assert result == "fid_1"

    @pytest.mark.asyncio
    async def test_upload_file_empty_response(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"file_infos": []}
        mock_resp.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.upload_file("ch_1", "test.txt", b"data")
        assert result == ""

    def test_client_properties(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        assert client.is_configured is True
        assert client.api_url == "https://mm.example.com/api/v4"
        assert client.ws_url == "wss://mm.example.com/api/v4/websocket"
        assert client.bot_user_id == ""

    def test_client_not_configured(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("", "")
        assert client.is_configured is False

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_http.aclose = AsyncMock()
        client._http = mock_http

        await client.close()
        mock_http.aclose.assert_called_once()
        assert client._http is None

    @pytest.mark.asyncio
    async def test_close_already_closed(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        await client.close()

    @pytest.mark.asyncio
    async def test_add_reaction(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        await client.add_reaction("user_1", "post_1", "thumbsup")
        body = mock_http.post.call_args.kwargs.get("json", {})
        assert body["emoji_name"] == "thumbsup"

    @pytest.mark.asyncio
    async def test_update_post(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "p1", "message": "updated"}
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.put = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.update_post("p1", "updated")
        assert result["message"] == "updated"

    @pytest.mark.asyncio
    async def test_delete_post(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.delete = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        await client.delete_post("p1")
        mock_http.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_teams_for_user(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("https://mm.example.com", "token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "t1", "name": "Team"}]
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.get_teams_for_user("u1")
        assert len(result) == 1

    def test_ws_url_http(self) -> None:
        from app.channels.providers.mattermost.api import MattermostClient

        client = MattermostClient("http://localhost:8065", "token")
        assert client.ws_url == "ws://localhost:8065/api/v4/websocket"
