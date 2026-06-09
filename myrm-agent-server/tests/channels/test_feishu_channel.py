"""FeishuChannel contract compliance + feature tests."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.feishu import FeishuChannel
from app.channels.providers.feishu.api import FeishuClient
from app.channels.providers.feishu.parser import FeishuInboundEvent
from app.channels.security.errors import WebhookResponseError
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)
from app.channels.types.components import (
    ActionButton,
    QuickReply,
)

from .channel_test_base import ChannelTestBase


class TestFeishuChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return FeishuChannel(app_id="test_app_id", app_secret="test_app_secret")


def _make_channel() -> FeishuChannel:
    return FeishuChannel(
        app_id="test_app_id",
        app_secret="test_app_secret",
        encrypt_key="test_encrypt_key",
    )


def _mock_client(ch: FeishuChannel, bot_open_id: str = "") -> AsyncMock:
    """Replace the channel's FeishuClient with a mock."""
    mock = AsyncMock(spec=FeishuClient)
    mock.bot_open_id = bot_open_id
    mock.is_configured = True
    mock._get_http.return_value = AsyncMock(spec=httpx.AsyncClient)
    ch._client = mock
    return mock


class TestVerifyWebhook:
    def test_no_encrypt_key_always_passes(self) -> None:
        ch = FeishuChannel(app_id="a", app_secret="s")
        assert ch.verify_webhook(b"body", "ts", "nonce", "any_sig") is True

    def test_valid_signature(self) -> None:
        ch = _make_channel()
        body = b'{"event_type":"test"}'
        timestamp = "1234567890"
        nonce = "abc123"
        prefix = (timestamp + nonce + "test_encrypt_key").encode("utf-8")
        expected = hashlib.sha256(prefix + body).hexdigest()
        assert ch.verify_webhook(body, timestamp, nonce, expected) is True

    def test_invalid_signature(self) -> None:
        ch = _make_channel()
        assert ch.verify_webhook(b"body", "ts", "nonce", "wrong_sig") is False


class TestHandleWebhookEvent:
    @pytest.mark.asyncio
    async def test_challenge_response(self) -> None:
        ch = _make_channel()
        result = await ch.handle_webhook_event({"challenge": "test_challenge_token"})
        assert result == {"challenge": "test_challenge_token"}

    @pytest.mark.asyncio
    async def test_message_event_emits_inbound(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user1"}, "sender_type": "user"},
                "message": {
                    "message_id": "om_msg1",
                    "message_type": "text",
                    "chat_id": "oc_chat1",
                    "chat_type": "p2p",
                    "content": json.dumps({"text": "hello bot"}),
                },
            },
        }
        result = await ch.handle_webhook_event(event_data)
        assert result is None
        assert len(received) == 1
        assert received[0].content == "hello bot"
        assert received[0].chat_id == "oc_chat1"

    @pytest.mark.asyncio
    async def test_bot_self_message_filtered(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_bot"}, "sender_type": "user"},
                "message": {
                    "message_id": "om_msg2",
                    "message_type": "text",
                    "chat_id": "oc_chat1",
                    "chat_type": "p2p",
                    "content": json.dumps({"text": "bot echo"}),
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_card_action_emits_inbound_with_toast(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "operator": {"open_id": "ou_user2"},
                "action": {"tag": "button", "value": {"type": "act", "action_id": "approve:req-1"}},
                "context": {"open_chat_id": "oc_chat2", "open_message_id": "om_msg3"},
            },
        }
        result = await ch.handle_webhook_event(event_data)
        assert result is not None
        assert "toast" in result
        assert len(received) == 1
        assert received[0].content == "approve:req-1"

    @pytest.mark.asyncio
    async def test_card_action_bot_self_filtered(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "operator": {"open_id": "ou_bot"},
                "action": {"tag": "button", "value": {"type": "qr", "data": "yes"}},
                "context": {"open_chat_id": "oc_chat2", "open_message_id": "om_msg4"},
            },
        }
        result = await ch.handle_webhook_event(event_data)
        assert result is not None
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_group_message_with_mention(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user3"}, "sender_type": "user"},
                "message": {
                    "message_id": "om_msg5",
                    "message_type": "text",
                    "chat_id": "oc_group1",
                    "chat_type": "group",
                    "content": json.dumps({"text": "@_user_1 help"}),
                    "mentions": [{"id": {"open_id": "ou_bot"}, "key": "@_user_1"}],
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 1
        assert received[0].is_group is True
        assert received[0].mentioned is True


class TestSend:
    @pytest.mark.asyncio
    async def test_send_text_message(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.send_message.return_value = "om_test_123"

        msg = OutboundMessage(
            channel="feishu",
            recipient_id="oc_chat1",
            content="Hello!",
            user_id="u1",
            metadata={"receive_type": "chat_id"},
        )
        mid = await ch.send(msg)
        assert mid == "om_test_123"
        mock.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_card_message(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.send_message.return_value = "om_test_123"

        msg = OutboundMessage(
            channel="feishu",
            recipient_id="oc_chat1",
            content="Choose:",
            user_id="u1",
            metadata={"receive_type": "chat_id"},
            quick_replies=(QuickReply(label="Yes", text="yes"),),
        )
        mid = await ch.send(msg)
        assert mid == "om_test_123"
        call_args = mock.send_message.call_args
        assert call_args[0][1] == "interactive"


class TestEditMessage:
    @pytest.mark.asyncio
    async def test_edit_text(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.edit_message.return_value = True

        await ch.edit_message("oc_chat1", "om_msg1", "updated text")
        mock.edit_message.assert_called_once()
        call_args = mock.edit_message.call_args
        assert call_args[0][1] == "interactive"

    @pytest.mark.asyncio
    async def test_edit_placeholder_with_card(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.edit_message.return_value = True

        msg = OutboundMessage(
            channel="feishu",
            recipient_id="oc_chat1",
            content="Final answer",
            user_id="u1",
            components=((ActionButton(label="OK", action_id="ok"),),),
        )
        await ch.edit_placeholder_message("oc_chat1", "om_msg1", msg)
        mock.edit_message.assert_called_once()
        call_args = mock.edit_message.call_args
        assert call_args[0][1] == "interactive"


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.ensure_token.return_value = "tok"
        mock.fetch_bot_info.return_value = "ou_bot"

        await ch.start()
        assert ch.status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_failure(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.ensure_token.side_effect = Exception("connection refused")

        await ch.start()
        assert ch.status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_start_no_credentials(self) -> None:
        # After validation was added to __init__, empty credentials now raise ValueError
        with pytest.raises(ValueError, match="app_id cannot be empty"):
            FeishuChannel(app_id="", app_secret="")

    @pytest.mark.asyncio
    async def test_health_check_running(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        mock = _mock_client(ch)
        mock.verify_connectivity.return_value = True

        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_idle(self) -> None:
        ch = _make_channel()
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.delete_message.return_value = True

        await ch.delete_message("oc_chat", "om_msg")
        mock.delete_message.assert_called_once()


class TestCapabilities:
    def test_buttons_enabled(self) -> None:
        ch = _make_channel()
        assert ch.capabilities.buttons is True
        assert ch.capabilities.quick_replies is True
        assert ch.capabilities.select_menus is True
        assert ch.capabilities.interactive_callback is True

    def test_typing_indicator_disabled(self) -> None:
        ch = _make_channel()
        assert ch.capabilities.typing_indicator is False

    def test_media_capabilities(self) -> None:
        ch = _make_channel()
        assert ch.capabilities.media is True
        assert ch.capabilities.file_upload is True
        assert ch.capabilities.edit is True
        assert ch.capabilities.delete is True


class TestResolveInboundMedia:
    """Tests for FeishuChannel._resolve_inbound_media()."""

    @pytest.mark.asyncio
    async def test_empty_keys_returns_empty_tuple(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        parsed = FeishuInboundEvent(
            sender_id="ou_user",
            chat_id="oc_chat",
            content="text only",
            message_id="om_1",
            msg_type="text",
            is_group=False,
            bot_mentioned=False,
        )
        result = await ch._resolve_inbound_media(parsed)
        assert result == ()

    @pytest.mark.asyncio
    async def test_image_download_success(self, tmp_path: object) -> None:
        ch = _make_channel()
        mock = _mock_client(ch, bot_open_id="ou_bot")
        mock.download_message_resource.return_value = b"\x89PNG_FAKE_DATA"
        parsed = FeishuInboundEvent(
            sender_id="ou_user",
            chat_id="oc_chat",
            content="check this image",
            message_id="om_msg_img",
            msg_type="image",
            is_group=False,
            bot_mentioned=False,
            image_keys=["img_key_001"],
        )
        result = await ch._resolve_inbound_media(parsed)
        assert len(result) == 1
        att = result[0]
        assert att.media_type == MediaType.IMAGE
        assert att.filename == "img_key_001.jpg"
        assert att.mime_type == "image/jpeg"
        assert att.path is not None
        mock.download_message_resource.assert_called_once_with("om_msg_img", "img_key_001", "image")

    @pytest.mark.asyncio
    async def test_image_fallback_to_download_image_when_no_message_id(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch, bot_open_id="ou_bot")
        mock.download_image.return_value = b"\x89PNG_DATA"
        parsed = FeishuInboundEvent(
            sender_id="ou_user",
            chat_id="oc_chat",
            content="image without msg id",
            message_id="",
            msg_type="image",
            is_group=False,
            bot_mentioned=False,
            image_keys=["img_key_002"],
        )
        result = await ch._resolve_inbound_media(parsed)
        assert len(result) == 1
        assert result[0].media_type == MediaType.IMAGE
        mock.download_image.assert_called_once_with("img_key_002")
        mock.download_message_resource.assert_not_called()

    @pytest.mark.asyncio
    async def test_file_download_success(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch, bot_open_id="ou_bot")
        mock.download_message_resource.return_value = b"FILE_CONTENT"
        parsed = FeishuInboundEvent(
            sender_id="ou_user",
            chat_id="oc_chat",
            content="check this file",
            message_id="om_msg_file",
            msg_type="file",
            is_group=False,
            bot_mentioned=False,
            media_keys=[("file_key_001", "report.pdf")],
        )
        result = await ch._resolve_inbound_media(parsed)
        assert len(result) == 1
        att = result[0]
        assert att.media_type == MediaType.DOCUMENT
        assert att.filename == "report.pdf"
        mock.download_message_resource.assert_called_once_with("om_msg_file", "file_key_001", "file")

    @pytest.mark.asyncio
    async def test_file_without_message_id_skipped(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        parsed = FeishuInboundEvent(
            sender_id="ou_user",
            chat_id="oc_chat",
            content="file without msg id",
            message_id="",
            msg_type="file",
            is_group=False,
            bot_mentioned=False,
            media_keys=[("file_key_002", "data.csv")],
        )
        result = await ch._resolve_inbound_media(parsed)
        assert result == ()

    @pytest.mark.asyncio
    async def test_individual_failure_does_not_block(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch, bot_open_id="ou_bot")
        mock.download_message_resource.side_effect = [
            RuntimeError("network error"),
            b"SECOND_IMAGE_DATA",
        ]
        parsed = FeishuInboundEvent(
            sender_id="ou_user",
            chat_id="oc_chat",
            content="two images",
            message_id="om_msg_multi",
            msg_type="image",
            is_group=False,
            bot_mentioned=False,
            image_keys=["fail_key", "ok_key"],
        )
        result = await ch._resolve_inbound_media(parsed)
        assert len(result) == 1
        assert result[0].filename == "ok_key.jpg"

    @pytest.mark.asyncio
    async def test_empty_data_returns_none(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch, bot_open_id="ou_bot")
        mock.download_message_resource.return_value = b""
        parsed = FeishuInboundEvent(
            sender_id="ou_user",
            chat_id="oc_chat",
            content="empty image",
            message_id="om_msg_empty",
            msg_type="image",
            is_group=False,
            bot_mentioned=False,
            image_keys=["empty_key"],
        )
        result = await ch._resolve_inbound_media(parsed)
        assert result == ()

    @pytest.mark.asyncio
    async def test_mixed_images_and_files(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch, bot_open_id="ou_bot")
        mock.download_message_resource.side_effect = [
            b"IMAGE_DATA",
            b"FILE_DATA",
        ]
        parsed = FeishuInboundEvent(
            sender_id="ou_user",
            chat_id="oc_chat",
            content="mixed media",
            message_id="om_msg_mixed",
            msg_type="post",
            is_group=False,
            bot_mentioned=False,
            image_keys=["img_mixed_001"],
            media_keys=[("file_mixed_001", "doc.xlsx")],
        )
        result = await ch._resolve_inbound_media(parsed)
        assert len(result) == 2
        types = {att.media_type for att in result}
        assert types == {MediaType.IMAGE, MediaType.DOCUMENT}


class TestHandleWebhookEventMedia:
    """Integration: handle_webhook_event with image messages."""

    @pytest.mark.asyncio
    async def test_image_message_carries_media_and_metadata(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch, bot_open_id="ou_bot")
        mock.download_message_resource.return_value = b"IMG_DATA"
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user1"}, "sender_type": "user"},
                "message": {
                    "message_id": "om_img_msg",
                    "message_type": "image",
                    "chat_id": "oc_chat1",
                    "chat_type": "p2p",
                    "content": json.dumps({"image_key": "img_key_abc"}),
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 1
        msg = received[0]
        assert msg.message_id == "om_img_msg"
        assert msg.metadata["message_id"] == "om_img_msg"
        assert msg.metadata["msg_type"] == "image"
        assert msg.metadata["image_keys"] == ["img_key_abc"]
        assert len(msg.media) == 1
        assert msg.media[0].media_type == MediaType.IMAGE

    @pytest.mark.asyncio
    async def test_text_message_has_empty_media(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user1"}, "sender_type": "user"},
                "message": {
                    "message_id": "om_text_msg",
                    "message_type": "text",
                    "chat_id": "oc_chat1",
                    "chat_type": "p2p",
                    "content": json.dumps({"text": "just text"}),
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 1
        assert received[0].media == ()
        assert received[0].metadata["message_id"] == "om_text_msg"


class TestFromCredentials:
    def test_defaults_to_webhook(self) -> None:
        ch = FeishuChannel.from_credentials({"app_id": "a", "app_secret": "s"})
        assert ch._transport == "webhook"

    def test_websocket_transport(self) -> None:
        ch = FeishuChannel.from_credentials(
            {"app_id": "a", "app_secret": "s", "transport": "websocket"},
        )
        assert ch._transport == "websocket"

    def test_invalid_transport_falls_back_to_webhook(self) -> None:
        ch = FeishuChannel.from_credentials(
            {"app_id": "a", "app_secret": "s", "transport": "garbage"},
        )
        assert ch._transport == "webhook"


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_clears_state(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        ch._status = ChannelStatus.RUNNING
        await ch.stop()
        assert ch.status == ChannelStatus.STOPPED
        mock.close.assert_called_once()


class TestVerify:
    @pytest.mark.asyncio
    async def test_challenge_skips_token_check(self) -> None:
        ch = FeishuChannel(app_id="a", app_secret="s", verification_token="tok")
        body = json.dumps({"challenge": "abc"}).encode()
        req = AsyncMock(spec=["state"])
        await ch.verify(req, body)

    @pytest.mark.asyncio
    async def test_valid_token_passes(self) -> None:
        ch = FeishuChannel(app_id="a", app_secret="s", verification_token="tok")
        body = json.dumps({"token": "tok"}).encode()
        req = AsyncMock(spec=["state"])
        await ch.verify(req, body)

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self) -> None:
        ch = FeishuChannel(app_id="a", app_secret="s", verification_token="tok")
        body = json.dumps({"token": "wrong"}).encode()
        req = AsyncMock(spec=["state"])
        req.state._webhook_trace_id = "trace-1"
        with pytest.raises(WebhookResponseError):
            await ch.verify(req, body)

    @pytest.mark.asyncio
    async def test_no_verification_token_passes(self) -> None:
        ch = FeishuChannel(app_id="a", app_secret="s")
        body = json.dumps({"token": "anything"}).encode()
        req = AsyncMock(spec=["state"])
        await ch.verify(req, body)


class TestSendPlaceholder:
    @pytest.mark.asyncio
    async def test_sends_thinking_card_and_inits_streaming(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.send_message.return_value = "om_placeholder"
        mock.streaming_card_create.return_value = True
        msg_id = await ch.send_placeholder("oc_chat1", "Thinking...")
        assert msg_id == "om_placeholder"
        assert "om_placeholder" in ch._streaming_card_ids

    @pytest.mark.asyncio
    async def test_streaming_init_failure_still_returns_msg_id(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.send_message.return_value = "om_placeholder2"
        mock.streaming_card_create.return_value = False
        msg_id = await ch.send_placeholder("oc_chat1", "Thinking...")
        assert msg_id == "om_placeholder2"
        assert "om_placeholder2" not in ch._streaming_card_ids


class TestStreaming:
    @pytest.mark.asyncio
    async def test_streaming_update_success(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        ch._streaming_card_ids["om_1"] = "card_1"
        ch._streaming_seq["om_1"] = 1
        mock.streaming_card_update.return_value = True
        ok = await ch._streaming_update("om_1", "new text")
        assert ok is True
        assert ch._streaming_seq["om_1"] == 2

    @pytest.mark.asyncio
    async def test_streaming_update_no_card_id(self) -> None:
        ch = _make_channel()
        _mock_client(ch)
        ok = await ch._streaming_update("om_missing", "text")
        assert ok is False

    @pytest.mark.asyncio
    async def test_streaming_finalize_cleans_up(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        ch._streaming_card_ids["om_1"] = "card_1"
        ch._streaming_seq["om_1"] = 3
        mock.streaming_card_update.return_value = True
        await ch._streaming_finalize("om_1", "final text")
        assert "om_1" not in ch._streaming_card_ids
        assert "om_1" not in ch._streaming_seq
        mock.streaming_card_update.assert_called_once_with("card_1", "final text", seq=4, is_final=True)

    @pytest.mark.asyncio
    async def test_streaming_finalize_noop_without_card_id(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        await ch._streaming_finalize("om_missing", "text")
        mock.streaming_card_update.assert_not_called()


class TestReactionInbound:
    """Tests for inbound reaction event handling (_handle_reaction_event)."""

    @pytest.mark.asyncio
    async def test_reaction_thumbsup(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.reaction_created_v1"},
            "event": {
                "message_id": "om_msg_target",
                "reaction_type": {"emoji_type": "THUMBSUP"},
                "operator_type": {
                    "operator_id": {"open_id": "ou_user1"},
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 1
        assert received[0].content == "\U0001f44d"
        assert received[0].message_id == "om_msg_target"
        assert received[0].metadata.get("reaction") is True
        assert received[0].metadata.get("target_message_id") == "om_msg_target"
        assert received[0].sender_id == "ou_user1"

    @pytest.mark.asyncio
    async def test_reaction_from_bot_filtered(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.reaction_created_v1"},
            "event": {
                "message_id": "om_msg_target",
                "reaction_type": {"emoji_type": "THUMBSUP"},
                "operator_type": {
                    "operator_id": {"open_id": "ou_bot"},
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_reaction_unknown_emoji_type_filtered(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.reaction_created_v1"},
            "event": {
                "message_id": "om_msg_target",
                "reaction_type": {"emoji_type": "UNKNOWN_EMOJI_XYZ"},
                "operator_type": {
                    "operator_id": {"open_id": "ou_user2"},
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_reaction_missing_message_id_filtered(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.reaction_created_v1"},
            "event": {
                "message_id": "",
                "reaction_type": {"emoji_type": "THUMBSUP"},
                "operator_type": {
                    "operator_id": {"open_id": "ou_user1"},
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_reaction_missing_operator_filtered(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.reaction_created_v1"},
            "event": {
                "message_id": "om_msg_target",
                "reaction_type": {"emoji_type": "THUMBSUP"},
                "operator_type": {},
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_reaction_heart_emoji(self) -> None:
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.reaction_created_v1"},
            "event": {
                "message_id": "om_msg_target_2",
                "reaction_type": {"emoji_type": "HEART"},
                "operator_type": {
                    "operator_id": {"open_id": "ou_user3"},
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 1
        assert received[0].content == "\u2764\ufe0f"

    @pytest.mark.asyncio
    async def test_reaction_type_not_dict_filtered(self) -> None:
        """reaction_type as non-dict should be handled gracefully."""
        ch = _make_channel()
        _mock_client(ch, bot_open_id="ou_bot")
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        event_data = {
            "header": {"event_type": "im.message.reaction_created_v1"},
            "event": {
                "message_id": "om_msg_target_3",
                "reaction_type": "THUMBSUP",
                "operator_type": {
                    "operator_id": {"open_id": "ou_user4"},
                },
            },
        }
        await ch.handle_webhook_event(event_data)
        assert len(received) == 0


class TestReactToMessage:
    @pytest.mark.asyncio
    async def test_add_reaction(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.add_reaction.return_value = "react_id_1"
        await ch.react_to_message("oc_chat1", "om_msg1", "\U0001f44d")
        mock.add_reaction.assert_called_once()
        assert ch._reaction_ids["om_msg1"] == "react_id_1"

    @pytest.mark.asyncio
    async def test_remove_reaction(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        ch._reaction_ids["om_msg1"] = "react_id_1"
        await ch.react_to_message("oc_chat1", "om_msg1", "")
        mock.delete_reaction.assert_called_once_with("om_msg1", "react_id_1")

    @pytest.mark.asyncio
    async def test_empty_message_id_skipped(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        await ch.react_to_message("oc_chat1", "", "")
        mock.add_reaction.assert_not_called()


class TestFetchReplyContext:
    @pytest.mark.asyncio
    async def test_no_parent_id(self) -> None:
        ch = _make_channel()
        _mock_client(ch)
        result = await ch._fetch_reply_context(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_parent_message(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.get_message.return_value = {"body": {"content": json.dumps({"text": "parent text"})}, "msg_type": "text"}
        result = await ch._fetch_reply_context("om_parent")
        assert result is not None
        assert "parent text" in result.content

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_empty(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.get_message.side_effect = RuntimeError("API error")
        result = await ch._fetch_reply_context("om_parent")
        assert result is None


class TestSendMedia:
    @pytest.mark.asyncio
    async def test_upload_and_send_image(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.upload_image.return_value = "img_uploaded_key"
        mock.send_message.return_value = "om_sent"
        att = MediaAttachment(
            media_type=MediaType.IMAGE,
            path="/tmp/test_img.jpg",
        )
        with patch("pathlib.Path.read_bytes", return_value=b"IMG_DATA"):
            mid = await ch._send_media("oc_chat", "chat_id", att)
        assert mid == "om_sent"
        mock.upload_image.assert_called_once_with(b"IMG_DATA")

    @pytest.mark.asyncio
    async def test_upload_and_send_file(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.upload_file.return_value = "file_uploaded_key"
        mock.send_message.return_value = "om_sent_file"
        att = MediaAttachment(
            media_type=MediaType.DOCUMENT,
            path="/tmp/test.pdf",
            filename="report.pdf",
        )
        with patch("pathlib.Path.read_bytes", return_value=b"FILE_DATA"):
            mid = await ch._send_media("oc_chat", "chat_id", att)
        assert mid == "om_sent_file"
        mock.upload_file.assert_called_once_with(b"FILE_DATA", "report.pdf")

    @pytest.mark.asyncio
    async def test_no_data_returns_none(self) -> None:
        ch = _make_channel()
        _mock_client(ch)
        att = MediaAttachment(media_type=MediaType.IMAGE)
        mid = await ch._send_media("oc_chat", "chat_id", att)
        assert mid is None


class TestDownloadAttachment:
    @pytest.mark.asyncio
    async def test_local_path(self) -> None:
        ch = _make_channel()
        _mock_client(ch)
        att = MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/test.jpg")
        with patch("pathlib.Path.read_bytes", return_value=b"LOCAL_DATA"):
            result = await ch._download_attachment(att)
        assert result == b"LOCAL_DATA"

    @pytest.mark.asyncio
    async def test_url_download(self) -> None:
        ch = _make_channel()
        mock = _mock_client(ch)
        mock.download_url.return_value = b"URL_DATA"
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png")
        result = await ch._download_attachment(att)
        assert result == b"URL_DATA"

    @pytest.mark.asyncio
    async def test_no_path_no_url_returns_none(self) -> None:
        ch = _make_channel()
        _mock_client(ch)
        att = MediaAttachment(media_type=MediaType.IMAGE)
        result = await ch._download_attachment(att)
        assert result is None


class TestCollectIssues:
    def test_no_credentials_reports_issue(self) -> None:
        # After validation was added to __init__, empty credentials now raise ValueError
        # So this test verifies that ValueError is raised when trying to create with empty credentials
        with pytest.raises(ValueError, match="app_id cannot be empty"):
            FeishuChannel(app_id="", app_secret="")

    def test_configured_no_issues(self) -> None:
        ch = _make_channel()
        issues = ch.collect_issues()
        assert len(issues) == 0

    def test_health_error_reported(self) -> None:
        ch = _make_channel()
        ch.health.last_error = "Connection lost"
        issues = ch.collect_issues()
        assert any("Connection lost" in i.message for i in issues)

    def test_ws_transport_missing_sdk_suggests_uv_sync(self) -> None:
        ch = FeishuChannel(
            app_id="test_app_id",
            app_secret="test_app_secret",
            encrypt_key="test_encrypt_key",
            transport="websocket",
        )
        with patch(
            "app.channels.providers.feishu.ws_transport.SDK_AVAILABLE",
            False,
        ):
            issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].fix == "uv sync --extra channels-sdk"
        assert "uv sync" in issues[0].message
