"""DingTalkChannel tests — contract, lifecycle, inbound, outbound, helpers, diagnostics."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.dingtalk import DingTalkChannel
from app.channels.providers.dingtalk.helpers import (
    filename_from_url,
    guess_filename,
    guess_mime_type,
    guess_upload_type,
    normalize_file_type,
    parse_callback,
    verify_signature,
)
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)
from app.channels.types.status import IssueKind, IssueSeverity

from .channel_test_base import ChannelTestBase

# ── Contract ──────────────────────────────────────────────────


class TestDingTalkChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return DingTalkChannel(app_key="test_key", app_secret="test_secret")


# ── Helpers ───────────────────────────────────────────────────


def _make_channel() -> DingTalkChannel:
    ch = DingTalkChannel(app_key="test_key", app_secret="test_secret", robot_code="robot1")
    ch._api._access_token = "mock_token"
    ch._api._token_expires_at = 9999999999.0
    return ch


def _text_event(
    content: str = "hello",
    sender_id: str = "user1",
    conversation_id: str = "conv1",
    conversation_type: str = "1",
    msg_id: str = "m1",
    at_users: list[dict[str, object]] | None = None,
    webhook_url: str | None = None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "msgtype": "text",
        "text": {"content": content},
        "senderStaffId": sender_id,
        "conversationId": conversation_id,
        "conversationType": conversation_type,
        "msgId": msg_id,
    }
    if at_users:
        event["atUsers"] = at_users
    if webhook_url:
        event["sessionWebhook"] = webhook_url
    return event


# ── Helpers module tests ──────────────────────────────────────


class TestDingTalkHelpers:
    def test_verify_signature_no_secret(self) -> None:
        assert verify_signature("", "12345", "any") is True

    def test_verify_signature_valid(self) -> None:
        import base64
        import hashlib
        import hmac as _hmac
        import time

        secret = "test_secret"
        ts = str(int(time.time() * 1000))
        string_to_sign = f"{ts}\n{secret}"
        digest = _hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
        sign = base64.b64encode(digest).decode()

        assert verify_signature(secret, ts, sign) is True

    def test_verify_signature_invalid(self) -> None:
        assert verify_signature("secret", "12345", "bad_sign") is False

    def test_parse_callback_text(self) -> None:
        result = parse_callback(_text_event(), "robot1")
        assert result is not None
        assert result["content"] == "hello"
        assert result["sender_id"] == "user1"
        assert result["is_group"] is False

    def test_parse_callback_group_with_mention(self) -> None:
        result = parse_callback(
            _text_event(
                content="@robot1 hello",
                conversation_type="2",
                at_users=[{"dingtalkId": "robot1"}],
            ),
            "robot1",
        )
        assert result is not None
        assert result["is_group"] is True
        assert result["mentioned"] is True
        assert "hello" in result["content"]

    def test_parse_callback_group_strip_at(self) -> None:
        result = parse_callback(
            _text_event(
                content="@bot hello world",
                conversation_type="2",
                at_users=[{"dingtalkId": "bot"}],
            ),
            "robot1",
        )
        assert result is not None
        assert result["content"] == "hello world"

    def test_parse_callback_rich_text(self) -> None:
        event: dict[str, object] = {
            "msgtype": "richText",
            "richText": {"richTextList": [{"text": "part1"}, {"text": "part2"}]},
            "senderStaffId": "u1",
            "conversationId": "c1",
            "conversationType": "1",
            "msgId": "m1",
        }
        result = parse_callback(event, "robot1")
        assert result is not None
        assert result["content"] == "part1part2"

    def test_parse_callback_rich_text_with_picture(self) -> None:
        event: dict[str, object] = {
            "msgtype": "richText",
            "richText": {
                "richTextList": [
                    {"type": "text", "text": "Look at this: "},
                    {"type": "picture", "downloadCode": "img_code_123"},
                    {"type": "text", "text": " what is it?"},
                ]
            },
            "senderStaffId": "u1",
            "conversationId": "c1",
            "conversationType": "1",
            "msgId": "m1",
        }
        result = parse_callback(event, "robot1")
        assert result is not None
        assert result["content"] == "Look at this:  what is it?"
        assert len(result["media"]) == 1
        assert result["media"][0].media_type == MediaType.IMAGE
        assert result["media"][0].url == "img_code_123"

    def test_parse_callback_rich_text_multiple_pictures(self) -> None:
        event: dict[str, object] = {
            "msgtype": "richText",
            "richText": {
                "richTextList": [
                    {"type": "picture", "downloadCode": "code_a"},
                    {"type": "text", "text": "Compare"},
                    {"type": "picture", "downloadCode": "code_b"},
                ]
            },
            "senderStaffId": "u1",
            "conversationId": "c1",
            "conversationType": "1",
            "msgId": "m1",
        }
        result = parse_callback(event, "robot1")
        assert result is not None
        assert result["content"] == "Compare"
        assert len(result["media"]) == 2
        assert result["media"][0].url == "code_a"
        assert result["media"][1].url == "code_b"

    def test_parse_callback_picture(self) -> None:
        event: dict[str, object] = {
            "msgtype": "picture",
            "content": {"downloadCode": "https://img.dingtalk.com/1.jpg"},
            "senderStaffId": "u1",
            "conversationId": "c1",
            "conversationType": "1",
            "msgId": "m1",
        }
        result = parse_callback(event, "robot1")
        assert result is not None
        assert len(result["media"]) == 1
        assert result["media"][0].media_type == MediaType.IMAGE

    def test_parse_callback_file(self) -> None:
        event: dict[str, object] = {
            "msgtype": "file",
            "content": {"fileName": "doc.pdf"},
            "senderStaffId": "u1",
            "conversationId": "c1",
            "conversationType": "1",
            "msgId": "m1",
        }
        result = parse_callback(event, "robot1")
        assert result is not None
        assert len(result["media"]) == 1
        assert result["media"][0].media_type == MediaType.DOCUMENT

    def test_parse_callback_empty_content(self) -> None:
        result = parse_callback(_text_event(content="  "), "robot1")
        assert result is None

    def test_guess_upload_type_image(self) -> None:
        assert guess_upload_type("photo.jpg") == "image"
        assert guess_upload_type("photo.PNG") == "image"

    def test_guess_upload_type_voice(self) -> None:
        assert guess_upload_type("audio.mp3") == "voice"

    def test_guess_upload_type_video(self) -> None:
        assert guess_upload_type("video.mp4") == "video"

    def test_guess_upload_type_file(self) -> None:
        assert guess_upload_type("doc.pdf") == "file"

    def test_normalize_file_type(self) -> None:
        assert normalize_file_type("photo.jpeg") == "jpg"
        assert normalize_file_type("photo.png") == "png"
        assert normalize_file_type("noext") == "bin"

    def test_filename_from_url(self) -> None:
        assert filename_from_url("https://example.com/path/photo.jpg") == "photo.jpg"
        assert filename_from_url("https://example.com/") == "download.bin"

    def test_guess_filename_path(self) -> None:
        att = MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/photo.jpg")
        assert guess_filename(att) == "photo.jpg"

    def test_guess_filename_url(self) -> None:
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/photo.jpg")
        assert guess_filename(att) == "photo.jpg"

    def test_guess_filename_none(self) -> None:
        att = MediaAttachment(media_type=MediaType.IMAGE)
        assert guess_filename(att) == "attachment"

    def test_guess_mime_type(self) -> None:
        assert "image" in guess_mime_type("photo.jpg")
        assert guess_mime_type("unknown") == "application/octet-stream"


# ── Lifecycle ─────────────────────────────────────────────────


class TestDingTalkLifecycle:
    @pytest.mark.asyncio
    async def test_start_no_credentials(self) -> None:
        ch = DingTalkChannel(app_key="", app_secret="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_token_failure(self) -> None:
        ch = DingTalkChannel(app_key="key", app_secret="secret")
        ch._api.refresh_token = AsyncMock(side_effect=Exception("auth fail"))
        ch._api.close = AsyncMock()
        await ch.start()
        assert ch._status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = DingTalkChannel(app_key="key", app_secret="secret")
        ch._api.refresh_token = AsyncMock()
        await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._stream_task is not None
        ch._stream_task.cancel()
        try:
            await ch._stream_task
        except (asyncio.CancelledError, Exception):
            pass
        ch._api.close = AsyncMock()
        await ch.stop()

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._api.close = AsyncMock()
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_cancels_stream_task(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._api.close = AsyncMock()

        async def _forever() -> None:
            await asyncio.sleep(999)

        ch._stream_task = asyncio.create_task(_forever())
        await ch.stop()
        assert ch._stream_task is None


class TestDingTalkHealthCheck:
    @pytest.mark.asyncio
    async def test_health_ok(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._api.ensure_token = AsyncMock()
        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_stopped(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_exception(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._api.ensure_token = AsyncMock(side_effect=Exception("net"))
        assert await ch.health_check() is False


# ── Diagnostics ───────────────────────────────────────────────


class TestDingTalkDiagnostics:
    def test_no_credentials(self) -> None:
        ch = DingTalkChannel(app_key="", app_secret="")
        issues = ch.collect_issues()
        assert any("App Key" in i.message for i in issues)
        assert any("App Secret" in i.message for i in issues)

    def test_no_robot_code_warning(self) -> None:
        ch = DingTalkChannel(app_key="key", app_secret="secret")
        issues = ch.collect_issues()
        assert any(i.severity == IssueSeverity.WARNING and "robot_code" in i.message for i in issues)

    def test_error_status(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.RUNTIME for i in issues)

    def test_health_error(self) -> None:
        ch = _make_channel()
        ch.health.last_error = "Connection refused"
        issues = ch.collect_issues()
        assert any("Connection refused" in i.message for i in issues)

    def test_healthy(self) -> None:
        ch = _make_channel()
        issues = ch.collect_issues()
        config_errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
        assert len(config_errors) == 0


# ── Inbound ───────────────────────────────────────────────────


class TestDingTalkInbound:
    @pytest.mark.asyncio
    async def test_webhook_text(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook(_text_event())
        assert len(emitted) == 1
        assert emitted[0].content == "hello"

    @pytest.mark.asyncio
    async def test_webhook_empty_filtered(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook(_text_event(content="  "))
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_webhook_group_registers(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]

        await ch.handle_webhook(_text_event(conversation_type="2"))
        assert "conv1" in ch._group_conversations

    def test_verify_webhook_signature(self) -> None:
        import base64
        import hashlib
        import hmac as _hmac
        import time

        ch = _make_channel()
        ts = str(int(time.time() * 1000))
        string_to_sign = f"{ts}\n{ch._app_secret}"
        digest = _hmac.new(ch._app_secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
        sign = base64.b64encode(digest).decode()

        assert ch.verify_webhook_signature(ts, sign) is True
        assert ch.verify_webhook_signature(ts, "bad") is False

    def test_register_group_eviction(self) -> None:
        ch = _make_channel()
        for i in range(501):
            ch._register_group(f"grp_{i}")
        assert len(ch._group_conversations) <= 500


# ── Outbound ──────────────────────────────────────────────────


class TestDingTalkSend:
    @pytest.mark.asyncio
    async def test_send_text_dm(self) -> None:
        ch = _make_channel()
        ch._api.ensure_token = AsyncMock()
        ch._api.send_dm_markdown = AsyncMock()

        msg = OutboundMessage(channel="dingtalk", recipient_id="user1", content="Hello", user_id="U")
        await ch.send(msg)
        ch._api.send_dm_markdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_text_group(self) -> None:
        ch = _make_channel()
        ch._api.ensure_token = AsyncMock()
        ch._api.send_group_markdown = AsyncMock()
        ch._group_conversations.add("grp1")

        msg = OutboundMessage(channel="dingtalk", recipient_id="grp1", content="Hello group", user_id="U")
        await ch.send(msg)
        ch._api.send_group_markdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_recipient(self) -> None:
        ch = _make_channel()
        ch._api.ensure_token = AsyncMock()

        msg = OutboundMessage(channel="dingtalk", recipient_id="", content="Hello", user_id="U")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_via_webhook(self) -> None:
        ch = _make_channel()
        ch._api.ensure_token = AsyncMock()
        ch._api.post_webhook = AsyncMock()

        msg = OutboundMessage(
            channel="dingtalk",
            recipient_id="user1",
            content="Hello",
            user_id="U",
            metadata={"webhookUrl": "https://oapi.dingtalk.com/robot/send?access_token=xxx"},
        )
        await ch.send(msg)
        ch._api.post_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_attachment_image_dm(self) -> None:
        ch = _make_channel()
        ch._api.ensure_token = AsyncMock()
        ch._api.send_image_dm = AsyncMock(return_value=True)

        msg = OutboundMessage(
            channel="dingtalk",
            recipient_id="user1",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg"),),
        )
        await ch.send(msg)
        ch._api.send_image_dm.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_attachment_group_markdown(self) -> None:
        ch = _make_channel()
        ch._api.ensure_token = AsyncMock()
        ch._api.send_group_markdown = AsyncMock()
        ch._group_conversations.add("grp1")

        msg = OutboundMessage(
            channel="dingtalk",
            recipient_id="grp1",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg"),),
        )
        await ch.send(msg)
        ch._api.send_group_markdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_attachment_fallback_text(self) -> None:
        ch = _make_channel()
        ch._api.ensure_token = AsyncMock()
        ch._api.send_image_dm = AsyncMock(return_value=False)
        ch._api.download_url = AsyncMock(return_value=None)
        ch._api.send_dm_markdown = AsyncMock()

        msg = OutboundMessage(
            channel="dingtalk",
            recipient_id="user1",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg"),),
        )
        await ch.send(msg)
        ch._api.send_dm_markdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_attachment_upload_flow(self) -> None:
        ch = _make_channel()
        ch._api.ensure_token = AsyncMock()
        ch._api.send_image_dm = AsyncMock(side_effect=[False, True])
        ch._api.download_url = AsyncMock(return_value=(b"imgdata", "image/jpeg"))
        ch._api.upload_media = AsyncMock(return_value="media_id_123")

        msg = OutboundMessage(
            channel="dingtalk",
            recipient_id="user1",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg"),),
        )
        await ch.send(msg)
        ch._api.upload_media.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_attachment_file_dm(self) -> None:
        ch = _make_channel()
        ch._api.ensure_token = AsyncMock()
        ch._api.download_url = AsyncMock(return_value=(b"filedata", "application/pdf"))
        ch._api.upload_media = AsyncMock(return_value="media_id_456")
        ch._api.send_file_dm = AsyncMock(return_value=True)

        msg = OutboundMessage(
            channel="dingtalk",
            recipient_id="user1",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type=MediaType.DOCUMENT, url="https://example.com/doc.pdf"),),
        )
        await ch.send(msg)
        ch._api.send_file_dm.assert_called_once()


# ── AI Card streaming ──────────────────────────────────────────


class TestDingTalkStreamingCard:
    @pytest.mark.asyncio
    async def test_send_placeholder_no_template(self) -> None:
        ch = _make_channel()
        result = await ch.send_placeholder("conv1", "Thinking...")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_placeholder_dm(self) -> None:
        ch = DingTalkChannel(
            app_key="key", app_secret="secret", robot_code="bot1", card_template_id="tpl.schema"
        )
        ch._api._access_token = "tok"
        ch._api._token_expires_at = float("inf")
        ch._chat_sender_map["conv1"] = "user123"
        ch._api.create_and_deliver_card = AsyncMock(return_value=True)

        result = await ch.send_placeholder("conv1", "Thinking...")
        assert result is not None
        assert result in ch._streaming_cards
        call = ch._api.create_and_deliver_card.call_args
        assert "IM_ROBOT.user123" in call.args[2]
        assert call.kwargs["is_group"] is False

    @pytest.mark.asyncio
    async def test_send_placeholder_group(self) -> None:
        ch = DingTalkChannel(
            app_key="key", app_secret="secret", robot_code="bot1", card_template_id="tpl.schema"
        )
        ch._api._access_token = "tok"
        ch._api._token_expires_at = float("inf")
        ch._group_conversations.add("grp1")
        ch._api.create_and_deliver_card = AsyncMock(return_value=True)

        result = await ch.send_placeholder("grp1", "Thinking...")
        assert result is not None
        call = ch._api.create_and_deliver_card.call_args
        assert "IM_GROUP.grp1" in call.args[2]
        assert call.kwargs["is_group"] is True

    @pytest.mark.asyncio
    async def test_send_placeholder_api_fail_returns_none(self) -> None:
        ch = DingTalkChannel(
            app_key="key", app_secret="secret", robot_code="bot1", card_template_id="tpl.schema"
        )
        ch._api._access_token = "tok"
        ch._api._token_expires_at = float("inf")
        ch._chat_sender_map["conv1"] = "user1"
        ch._api.create_and_deliver_card = AsyncMock(return_value=False)

        result = await ch.send_placeholder("conv1", "Thinking...")
        assert result is None
        assert len(ch._streaming_cards) == 0

    @pytest.mark.asyncio
    async def test_edit_message_streaming(self) -> None:
        ch = DingTalkChannel(
            app_key="key", app_secret="secret", robot_code="bot1", card_template_id="tpl.schema"
        )
        ch._api._access_token = "tok"
        ch._api._token_expires_at = float("inf")
        ch._api.streaming_update = AsyncMock(return_value=True)
        ch._streaming_cards["track1"] = "track1"

        await ch.edit_message("conv1", "track1", "Hello partial...")
        ch._api.streaming_update.assert_called_once_with("track1", "content", "Hello partial...", is_finalize=False)

    @pytest.mark.asyncio
    async def test_edit_message_non_streaming_noop(self) -> None:
        ch = _make_channel()
        ch._api.streaming_update = AsyncMock()

        await ch.edit_message("conv1", "unknown_id", "text")
        ch._api.streaming_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_placeholder_message_finalize(self) -> None:
        ch = DingTalkChannel(
            app_key="key", app_secret="secret", robot_code="bot1", card_template_id="tpl.schema"
        )
        ch._api._access_token = "tok"
        ch._api._token_expires_at = float("inf")
        ch._api.streaming_update = AsyncMock(return_value=True)
        ch._streaming_cards["track1"] = "track1"

        msg = OutboundMessage(channel="dingtalk", recipient_id="conv1", content="Final answer", user_id="U")
        await ch.edit_placeholder_message("conv1", "track1", msg)
        ch._api.streaming_update.assert_called_once_with("track1", "content", "Final answer", is_finalize=True)
        assert "track1" not in ch._streaming_cards

    @pytest.mark.asyncio
    async def test_finalize_active_cards(self) -> None:
        ch = DingTalkChannel(
            app_key="key", app_secret="secret", robot_code="bot1", card_template_id="tpl.schema"
        )
        ch._api._access_token = "tok"
        ch._api._token_expires_at = float("inf")
        ch._api.streaming_update = AsyncMock(return_value=True)
        ch._streaming_cards["track_old1"] = "track_old1"
        ch._streaming_cards["track_old2"] = "track_old2"

        await ch._finalize_active_cards()
        assert len(ch._streaming_cards) == 0
        assert ch._api.streaming_update.call_count == 2

    @pytest.mark.asyncio
    async def test_send_placeholder_finalizes_old_cards(self) -> None:
        ch = DingTalkChannel(
            app_key="key", app_secret="secret", robot_code="bot1", card_template_id="tpl.schema"
        )
        ch._api._access_token = "tok"
        ch._api._token_expires_at = float("inf")
        ch._chat_sender_map["conv1"] = "user1"
        ch._streaming_cards["old_track"] = "old_track"
        ch._api.streaming_update = AsyncMock(return_value=True)
        ch._api.create_and_deliver_card = AsyncMock(return_value=True)

        result = await ch.send_placeholder("conv1", "New thinking...")
        assert result is not None
        finalize_calls = [c for c in ch._api.streaming_update.call_args_list if c.kwargs.get("is_finalize") is True]
        assert len(finalize_calls) >= 1

    @pytest.mark.asyncio
    async def test_stop_finalizes_cards(self) -> None:
        ch = DingTalkChannel(
            app_key="key", app_secret="secret", robot_code="bot1", card_template_id="tpl.schema"
        )
        ch._api._access_token = "tok"
        ch._api._token_expires_at = float("inf")
        ch._status = ChannelStatus.RUNNING
        ch._streaming_cards["track1"] = "track1"
        ch._api.streaming_update = AsyncMock(return_value=True)
        ch._api.close = AsyncMock()

        await ch.stop()
        ch._api.streaming_update.assert_called_once()
        assert len(ch._streaming_cards) == 0

    @pytest.mark.asyncio
    async def test_inbound_caches_sender_for_dm(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]

        await ch.handle_webhook(_text_event(sender_id="staff_1", conversation_id="conv_dm"))
        assert ch._chat_sender_map.get("conv_dm") == "staff_1"

    @pytest.mark.asyncio
    async def test_inbound_group_does_not_cache_sender(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]

        await ch.handle_webhook(_text_event(sender_id="staff_1", conversation_id="conv_grp", conversation_type="2"))
        assert "conv_grp" not in ch._chat_sender_map

    def test_credential_spec_has_card_template(self) -> None:
        fields = dict(DingTalkChannel.credential_spec.fields)
        assert "card_template_id" in fields
        field = fields["card_template_id"]
        assert field.required is False
        assert field.is_sensitive is False
        assert field.default == ""

    def test_capabilities_edit_enabled(self) -> None:
        assert DingTalkChannel.capabilities.edit is True


# ── Read media ────────────────────────────────────────────────


class TestDingTalkReadMedia:
    @pytest.mark.asyncio
    async def test_read_from_url(self) -> None:
        ch = _make_channel()
        ch._api.download_url = AsyncMock(return_value=(b"data", "image/jpeg"))

        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/photo.jpg")
        data, filename, mime = await ch._read_media(att)
        assert data == b"data"
        assert filename == "photo.jpg"

    @pytest.mark.asyncio
    async def test_read_from_path(self) -> None:
        import tempfile

        ch = _make_channel()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image")
            f.flush()

        att = MediaAttachment(media_type=MediaType.IMAGE, path=f.name)
        data, filename, mime = await ch._read_media(att)
        assert data == b"fake image"
        assert "image" in mime

    @pytest.mark.asyncio
    async def test_read_no_source(self) -> None:
        ch = _make_channel()
        att = MediaAttachment(media_type=MediaType.IMAGE)
        data, filename, mime = await ch._read_media(att)
        assert data is None

    @pytest.mark.asyncio
    async def test_read_path_not_found(self) -> None:
        ch = _make_channel()
        att = MediaAttachment(media_type=MediaType.IMAGE, path="/nonexistent/file.png")
        data, filename, mime = await ch._read_media(att)
        assert data is None


# ---------------------------------------------------------------------------
# DingTalkApiClient (api.py) direct tests
# ---------------------------------------------------------------------------

import httpx  # noqa: E402

from app.channels.core.exceptions import ChannelAuthError  # noqa: E402
from app.channels.providers.dingtalk.api import (  # noqa: E402
    DingTalkApiClient,
)


def _mock_dt_client() -> DingTalkApiClient:
    """Create a DingTalkApiClient with mocked HTTP and pre-set token."""
    client = DingTalkApiClient("key", "secret", robot_code="robot1")
    client._access_token = "tok"
    client._token_expires_at = float("inf")
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.is_closed = False
    client._http = mock_http
    return client


class TestDingTalkApiClient:
    @pytest.mark.asyncio
    async def test_refresh_token_success(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"accessToken": "new_tok", "expireIn": 7200}
        client._http.post.return_value = resp

        await client.refresh_token()
        assert client._access_token == "new_tok"
        assert client._token_expires_at > 0

    @pytest.mark.asyncio
    async def test_refresh_token_failure(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 401
        client._http.post.return_value = resp

        with pytest.raises(ChannelAuthError):
            await client.refresh_token()

    @pytest.mark.asyncio
    async def test_ensure_token_cached(self) -> None:
        client = _mock_dt_client()
        await client.ensure_token()
        client._http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_token_expired(self) -> None:
        client = _mock_dt_client()
        client._token_expires_at = 0.0
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"accessToken": "refreshed", "expireIn": 7200}
        client._http.post.return_value = resp

        await client.ensure_token()
        assert client._access_token == "refreshed"

    @pytest.mark.asyncio
    async def test_post_robot_success(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.post_robot("https://api.dingtalk.com/v1.0/test", {"key": "val"})
        assert result is True

    @pytest.mark.asyncio
    async def test_post_robot_failure(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "Bad Request"
        client._http.post.return_value = resp

        result = await client.post_robot("https://api.dingtalk.com/v1.0/test", {"key": "val"})
        assert result is False

    @pytest.mark.asyncio
    async def test_post_webhook_success(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.post_webhook("https://oapi.dingtalk.com/webhook", {"text": "hi"})
        assert result is True

    @pytest.mark.asyncio
    async def test_post_webhook_failure(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 500
        client._http.post.return_value = resp

        result = await client.post_webhook("https://oapi.dingtalk.com/webhook", {"text": "hi"})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_dm_markdown(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.send_dm_markdown("user1", "Title", "**bold**")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_group_markdown(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.send_group_markdown("conv1", "Title", "text")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_image_dm(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.send_image_dm("user1", "https://img.com/a.png")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_file_dm(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.send_file_dm("user1", "media123", "report.pdf")
        assert result is True

    @pytest.mark.asyncio
    async def test_upload_media_success(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.json.return_value = {"media_id": "mid_1"}
        client._http.post.return_value = resp

        result = await client.upload_media(b"data", "image", "img.png", "image/png")
        assert result == "mid_1"

    @pytest.mark.asyncio
    async def test_upload_media_failure(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.json.return_value = {"errcode": 1, "errmsg": "fail"}
        client._http.post.return_value = resp

        result = await client.upload_media(b"data", "image", "img.png", "image/png")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_url_success(self) -> None:
        client = _mock_dt_client()
        from app.channels.media import MediaDownloadResult

        with patch(
            "app.channels.media.MediaDownloader.download",
            new_callable=AsyncMock,
            return_value=MediaDownloadResult(
                success=True,
                data=b"content",
                content_type="image/jpeg",
                error=None,
                url="https://example.com/img.jpg",
                size_bytes=7,
            ),
        ):
            result = await client.download_url("https://example.com/img.jpg")
        assert result is not None
        assert result[0] == b"content"

    @pytest.mark.asyncio
    async def test_download_url_failure(self) -> None:
        client = _mock_dt_client()
        from app.channels.media import MediaDownloadResult

        with patch(
            "app.channels.media.MediaDownloader.download",
            new_callable=AsyncMock,
            return_value=MediaDownloadResult(
                success=False,
                data=None,
                content_type=None,
                error=Exception("Failed"),
                url="https://example.com/missing.jpg",
                size_bytes=0,
            ),
        ):
            result = await client.download_url("https://example.com/missing.jpg")
        assert result is None

    @pytest.mark.asyncio
    async def test_open_stream_connection_success(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"endpoint": "wss://stream.dingtalk.com", "ticket": "tk_1"}
        client._http.post.return_value = resp

        endpoint, ticket = await client.open_stream_connection()
        assert endpoint == "wss://stream.dingtalk.com"
        assert ticket == "tk_1"

    @pytest.mark.asyncio
    async def test_open_stream_connection_failure(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 403
        client._http.post.return_value = resp

        with pytest.raises(ChannelAuthError):
            await client.open_stream_connection()

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        client = _mock_dt_client()
        await client.close()
        client._http.aclose.assert_called_once()

    def test_access_token_property(self) -> None:
        client = _mock_dt_client()
        assert client.access_token == "tok"

    @pytest.mark.asyncio
    async def test_create_and_deliver_card_success(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.create_and_deliver_card(
            "tpl_123", "track_abc", "dtv1.card//IM_GROUP.conv1", is_group=True
        )
        assert result is True
        call_kwargs = client._http.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["cardTemplateId"] == "tpl_123"
        assert body["outTrackId"] == "track_abc"
        assert "imGroupOpenSpaceModel" in body

    @pytest.mark.asyncio
    async def test_create_and_deliver_card_dm(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.create_and_deliver_card(
            "tpl_123", "track_dm", "dtv1.card//IM_ROBOT.user1", is_group=False
        )
        assert result is True
        call_kwargs = client._http.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "imRobotOpenSpaceModel" in body
        assert "imRobotOpenDeliverModel" in body

    @pytest.mark.asyncio
    async def test_create_and_deliver_card_failure(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "Bad Request"
        client._http.post.return_value = resp

        result = await client.create_and_deliver_card(
            "tpl_123", "track_fail", "dtv1.card//IM_GROUP.conv1", is_group=True
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_streaming_update_success(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.put.return_value = resp

        result = await client.streaming_update("track_abc", "content", "Hello world")
        assert result is True
        call_kwargs = client._http.put.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["outTrackId"] == "track_abc"
        assert body["content"] == "Hello world"
        assert body["isFull"] is True
        assert body["isFinalize"] is False

    @pytest.mark.asyncio
    async def test_streaming_update_finalize(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.put.return_value = resp

        result = await client.streaming_update("track_abc", "content", "Done", is_finalize=True)
        assert result is True
        call_kwargs = client._http.put.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["isFinalize"] is True

    @pytest.mark.asyncio
    async def test_streaming_update_failure(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        client._http.put.return_value = resp

        result = await client.streaming_update("track_abc", "content", "text")
        assert result is False

    @pytest.mark.asyncio
    async def test_resolve_download_code_success(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"downloadUrl": "https://dtfile.com/tmp/img.jpg"}
        client._http.post.return_value = resp

        url = await client.resolve_download_code("code_abc123")
        assert url == "https://dtfile.com/tmp/img.jpg"
        call_kwargs = client._http.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["downloadCode"] == "code_abc123"
        assert body["robotCode"] == "robot1"

    @pytest.mark.asyncio
    async def test_resolve_download_code_failure(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 403
        resp.text = "Forbidden"
        client._http.post.return_value = resp

        url = await client.resolve_download_code("bad_code")
        assert url is None

    @pytest.mark.asyncio
    async def test_resolve_download_code_empty_url(self) -> None:
        client = _mock_dt_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"downloadUrl": ""}
        client._http.post.return_value = resp

        url = await client.resolve_download_code("code_empty")
        assert url is None


class TestDingTalkMarkdownNormalize:
    """Test DingTalk-specific markdown normalization."""

    def test_numbered_list_blank_line(self) -> None:
        text = "Some intro text\n1. First item\n2. Second item"
        result = DingTalkChannel._normalize_dingtalk_markdown(text)
        assert "\n\n1. First item" in result

    def test_numbered_list_already_has_blank(self) -> None:
        text = "Some intro text\n\n1. First item\n2. Second item"
        result = DingTalkChannel._normalize_dingtalk_markdown(text)
        lines = result.split("\n")
        assert lines.count("") == 1

    def test_indented_code_fence_dedent(self) -> None:
        text = "text\n    ```python\n    code\n    ```"
        result = DingTalkChannel._normalize_dingtalk_markdown(text)
        assert "```python" in result
        assert "    ```python" not in result

    def test_no_change_normal_text(self) -> None:
        text = "Hello world\n\nThis is normal text."
        result = DingTalkChannel._normalize_dingtalk_markdown(text)
        assert result == text

    def test_consecutive_numbered_items_no_extra_blank(self) -> None:
        text = "1. First\n2. Second\n3. Third"
        result = DingTalkChannel._normalize_dingtalk_markdown(text)
        assert result == text


class TestDingTalkResolveMediaCodes:
    """Test inbound download_code → URL resolution."""

    @pytest.mark.asyncio
    async def test_resolve_media_codes_converts_download_code(self) -> None:
        ch = DingTalkChannel(app_key="k", app_secret="s")
        ch._api = MagicMock()
        ch._api.resolve_download_code = AsyncMock(
            return_value="https://dtfile.com/resolved.jpg"
        )

        msg = InboundMessage(
            channel="dingtalk",
            chat_id="conv1",
            sender_id="user1",
            content="Look at this",
            is_group=False,
            mentioned=False,
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="code_xyz"),),
            metadata={},
            message_id="msg1",
        )
        result = await ch._resolve_media_codes(msg)
        assert result.media[0].url == "https://dtfile.com/resolved.jpg"
        ch._api.resolve_download_code.assert_called_once_with("code_xyz")

    @pytest.mark.asyncio
    async def test_resolve_media_codes_skips_real_urls(self) -> None:
        ch = DingTalkChannel(app_key="k", app_secret="s")
        ch._api = MagicMock()
        ch._api.resolve_download_code = AsyncMock()

        msg = InboundMessage(
            channel="dingtalk",
            chat_id="conv1",
            sender_id="user1",
            content="",
            is_group=False,
            mentioned=False,
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://real.url/img.png"),),
            metadata={},
            message_id="msg2",
        )
        result = await ch._resolve_media_codes(msg)
        assert result.media[0].url == "https://real.url/img.png"
        ch._api.resolve_download_code.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_media_codes_fallback_on_failure(self) -> None:
        ch = DingTalkChannel(app_key="k", app_secret="s")
        ch._api = MagicMock()
        ch._api.resolve_download_code = AsyncMock(return_value=None)

        msg = InboundMessage(
            channel="dingtalk",
            chat_id="conv1",
            sender_id="user1",
            content="",
            is_group=False,
            mentioned=False,
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="bad_code"),),
            metadata={},
            message_id="msg3",
        )
        result = await ch._resolve_media_codes(msg)
        assert result.media[0].url == "bad_code"

    @pytest.mark.asyncio
    async def test_resolve_media_codes_no_media(self) -> None:
        ch = DingTalkChannel(app_key="k", app_secret="s")
        msg = InboundMessage(
            channel="dingtalk",
            chat_id="conv1",
            sender_id="user1",
            content="text only",
            is_group=False,
            mentioned=False,
            media=(),
            metadata={},
            message_id="msg4",
        )
        result = await ch._resolve_media_codes(msg)
        assert result is msg
