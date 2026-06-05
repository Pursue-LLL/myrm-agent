"""LINEChannel tests — contract compliance, inbound parsing, outbound, diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.core.allow_policy import AllowPolicy, ChatPolicy
from app.channels.core.base import BaseChannel
from app.channels.providers.line import LINEChannel, _ReplyToken
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    QuickReply,
)

from .channel_test_base import ChannelTestBase

# ---------------------------------------------------------------------------
# Contract compliance (ChannelTestBase)
# ---------------------------------------------------------------------------


class TestLINEChannelBase(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return LINEChannel(channel_access_token="test-token", channel_secret="test-secret")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel() -> tuple[LINEChannel, list[InboundMessage]]:
    ch = LINEChannel(channel_access_token="test-token", channel_secret="test-secret")
    ch.allow_policy = AllowPolicy(group_policy=ChatPolicy.ALLOW)
    received: list[InboundMessage] = []

    async def _handler(msg: InboundMessage) -> None:
        received.append(msg)

    ch.set_inbound_handler(_handler)
    return ch, received


def _make_event(
    *,
    msg_type: str = "text",
    text: str = "hello",
    source_type: str = "user",
    user_id: str = "U1234",
    group_id: str = "",
    room_id: str = "",
    reply_token: str = "rt-1",
    message_id: str = "msg-001",
    mention: dict[str, object] | None = None,
    quote_token: str = "",
    file_name: str = "",
) -> dict[str, object]:
    source: dict[str, object] = {"type": source_type, "userId": user_id}
    if group_id:
        source["groupId"] = group_id
    if room_id:
        source["roomId"] = room_id

    message: dict[str, object] = {"id": message_id, "type": msg_type}
    if msg_type == "text":
        message["text"] = text
    if mention:
        message["mention"] = mention
    if quote_token:
        message["quoteToken"] = quote_token
    if file_name:
        message["fileName"] = file_name

    return {
        "events": [
            {
                "type": "message",
                "replyToken": reply_token,
                "source": source,
                "message": message,
                "timestamp": 1700000000000,
            },
        ],
    }


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


class TestWebhookSignature:
    def test_no_secret_always_valid(self) -> None:
        ch = LINEChannel(channel_access_token="tok")
        assert ch.verify_signature(b"any body", "any sig") is True

    def test_valid_signature(self) -> None:
        import base64
        import hashlib
        import hmac as _hmac

        secret = "test-secret"
        body = b'{"events":[]}'
        digest = _hmac.new(secret.encode(), body, hashlib.sha256).digest()
        sig = base64.b64encode(digest).decode()

        ch = LINEChannel(channel_access_token="tok", channel_secret=secret)
        assert ch.verify_signature(body, sig) is True

    def test_invalid_signature(self) -> None:
        ch = LINEChannel(channel_access_token="tok", channel_secret="secret")
        assert ch.verify_signature(b"body", "bad-sig") is False


# ---------------------------------------------------------------------------
# Inbound parsing — text messages
# ---------------------------------------------------------------------------


class TestInboundText:
    @pytest.mark.asyncio
    async def test_dm_text_message(self) -> None:
        ch, received = _make_channel()
        body = _make_event(text="hi there")
        await ch.handle_webhook(body)
        assert len(received) == 1
        msg = received[0]
        assert msg.content == "hi there"
        assert msg.sender_id == "U1234"
        assert msg.chat_id == "U1234"
        assert msg.is_group is False

    @pytest.mark.asyncio
    async def test_group_text_message(self) -> None:
        ch, received = _make_channel()
        body = _make_event(
            source_type="group",
            group_id="C9999",
            text="hello group",
        )
        await ch.handle_webhook(body)
        assert len(received) == 1
        assert received[0].chat_id == "C9999"
        assert received[0].is_group is True

    @pytest.mark.asyncio
    async def test_room_message(self) -> None:
        ch, received = _make_channel()
        body = _make_event(source_type="room", room_id="R5555", text="room msg")
        await ch.handle_webhook(body)
        assert len(received) == 1
        assert received[0].chat_id == "R5555"
        assert received[0].is_group is True

    @pytest.mark.asyncio
    async def test_empty_text_filtered(self) -> None:
        ch, received = _make_channel()
        body = _make_event(text="   ")
        await ch.handle_webhook(body)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_sticker_message(self) -> None:
        ch, received = _make_channel()
        body = _make_event(msg_type="sticker")
        await ch.handle_webhook(body)
        assert len(received) == 1
        assert received[0].content == "[sticker]"

    @pytest.mark.asyncio
    async def test_location_message(self) -> None:
        ch, received = _make_channel()
        body = _make_event(msg_type="location")
        await ch.handle_webhook(body)
        assert len(received) == 1
        assert received[0].content == "[location]"


# ---------------------------------------------------------------------------
# Inbound parsing — media
# ---------------------------------------------------------------------------


class TestInboundMedia:
    @pytest.mark.asyncio
    async def test_image_message_has_download_url(self) -> None:
        ch, received = _make_channel()
        body = _make_event(msg_type="image", message_id="img-001")
        await ch.handle_webhook(body)
        assert len(received) == 1
        msg = received[0]
        assert len(msg.media) == 1
        assert msg.media[0].media_type == MediaType.IMAGE
        assert "img-001" in (msg.media[0].url or "")

    @pytest.mark.asyncio
    async def test_video_message(self) -> None:
        ch, received = _make_channel()
        body = _make_event(msg_type="video", message_id="vid-001")
        await ch.handle_webhook(body)
        assert received[0].media[0].media_type == MediaType.VIDEO

    @pytest.mark.asyncio
    async def test_audio_message(self) -> None:
        ch, received = _make_channel()
        body = _make_event(msg_type="audio", message_id="aud-001")
        await ch.handle_webhook(body)
        assert received[0].media[0].media_type == MediaType.AUDIO

    @pytest.mark.asyncio
    async def test_file_message_with_filename(self) -> None:
        ch, received = _make_channel()
        body = _make_event(msg_type="file", message_id="file-001", file_name="doc.pdf")
        await ch.handle_webhook(body)
        assert received[0].media[0].media_type == MediaType.DOCUMENT
        assert received[0].media[0].filename == "doc.pdf"


# ---------------------------------------------------------------------------
# Self-message filtering
# ---------------------------------------------------------------------------


class TestSelfMessageFilter:
    @pytest.mark.asyncio
    async def test_own_user_id_filtered(self) -> None:
        ch, received = _make_channel()
        ch._bot_user_id = "U1234"
        body = _make_event(user_id="U1234", text="self msg")
        await ch.handle_webhook(body)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_other_user_not_filtered(self) -> None:
        ch, received = _make_channel()
        ch._bot_user_id = "Ubot"
        body = _make_event(user_id="U1234", text="user msg")
        await ch.handle_webhook(body)
        assert len(received) == 1


# ---------------------------------------------------------------------------
# Mention detection
# ---------------------------------------------------------------------------


class TestMentionDetection:
    @pytest.mark.asyncio
    async def test_is_self_mentionee(self) -> None:
        ch, received = _make_channel()
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="@bot hello",
            mention={"mentionees": [{"isSelf": True, "index": 0, "length": 4}]},
        )
        await ch.handle_webhook(body)
        assert len(received) == 1
        assert received[0].mentioned is True

    @pytest.mark.asyncio
    async def test_user_id_match_mentionee(self) -> None:
        ch, received = _make_channel()
        ch._bot_user_id = "Ubot123"
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="@bot hello",
            mention={"mentionees": [{"userId": "Ubot123", "index": 0, "length": 4}]},
        )
        await ch.handle_webhook(body)
        assert received[0].mentioned is True

    @pytest.mark.asyncio
    async def test_all_type_mentionee(self) -> None:
        ch, received = _make_channel()
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="@all hello",
            mention={"mentionees": [{"type": "all", "index": 0, "length": 4}]},
        )
        await ch.handle_webhook(body)
        assert received[0].mentioned is True

    @pytest.mark.asyncio
    async def test_display_name_text_fallback(self) -> None:
        ch, received = _make_channel()
        ch._bot_display_name = "MyBot"
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="@MyBot what's up",
        )
        await ch.handle_webhook(body)
        assert received[0].mentioned is True

    @pytest.mark.asyncio
    async def test_no_mention_in_group(self) -> None:
        ch, received = _make_channel()
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="just chatting",
        )
        await ch.handle_webhook(body)
        assert received[0].mentioned is False


# ---------------------------------------------------------------------------
# Mention stripping
# ---------------------------------------------------------------------------


class TestMentionStripping:
    @pytest.mark.asyncio
    async def test_strip_self_mention_from_text(self) -> None:
        ch, received = _make_channel()
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="@bot how are you",
            mention={"mentionees": [{"isSelf": True, "index": 0, "length": 4}]},
        )
        await ch.handle_webhook(body)
        assert received[0].content == "how are you"

    @pytest.mark.asyncio
    async def test_strip_display_name_fallback(self) -> None:
        ch, received = _make_channel()
        ch._bot_display_name = "Bot"
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="@Bot help me",
        )
        await ch.handle_webhook(body)
        assert received[0].content == "help me"


# ---------------------------------------------------------------------------
# Postback handling
# ---------------------------------------------------------------------------


class TestPostbackHandling:
    @pytest.mark.asyncio
    async def test_postback_event(self) -> None:
        ch, received = _make_channel()
        body = {
            "events": [
                {
                    "type": "postback",
                    "replyToken": "rt-pb",
                    "source": {"type": "user", "userId": "U1234"},
                    "postback": {"data": "action=buy&item=123"},
                    "timestamp": 1700000000000,
                },
            ],
        }
        await ch.handle_webhook(body)
        assert len(received) == 1
        assert received[0].content == "action=buy&item=123"

    @pytest.mark.asyncio
    async def test_empty_postback_filtered(self) -> None:
        ch, received = _make_channel()
        body = {
            "events": [
                {
                    "type": "postback",
                    "source": {"type": "user", "userId": "U1234"},
                    "postback": {"data": ""},
                },
            ],
        }
        await ch.handle_webhook(body)
        assert len(received) == 0


# ---------------------------------------------------------------------------
# Reply token management
# ---------------------------------------------------------------------------


class TestReplyToken:
    @pytest.mark.asyncio
    async def test_reply_token_stored(self) -> None:
        ch, _received = _make_channel()
        body = _make_event(reply_token="rt-abc")
        await ch.handle_webhook(body)
        assert "U1234" in ch._reply_tokens
        assert ch._reply_tokens["U1234"].token == "rt-abc"

    def test_reply_token_expiry(self) -> None:
        from app.channels.providers.line import _ReplyToken

        token = _ReplyToken("test")
        assert token.expired is False
        token.created_at -= 30.0
        assert token.expired is True


# ---------------------------------------------------------------------------
# Quote token
# ---------------------------------------------------------------------------


class TestQuoteToken:
    @pytest.mark.asyncio
    async def test_quote_token_stored(self) -> None:
        ch, _received = _make_channel()
        body = _make_event(quote_token="qt-xyz")
        await ch.handle_webhook(body)
        assert ch._quote_tokens.get("U1234") == "qt-xyz"


# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------


class TestLifecycleEvents:
    @pytest.mark.asyncio
    async def test_follow_event(self) -> None:
        ch, _received = _make_channel()
        events_received: list[dict[str, object]] = []
        ch.on("line:follow", lambda _name, data: events_received.append(data))

        body = {
            "events": [
                {
                    "type": "follow",
                    "source": {"type": "user", "userId": "U9999"},
                },
            ],
        }
        await ch.handle_webhook(body)
        assert len(events_received) == 1
        assert events_received[0]["source_type"] == "user"

    @pytest.mark.asyncio
    async def test_join_event(self) -> None:
        ch, _received = _make_channel()
        events_received: list[dict[str, object]] = []
        ch.on("line:join", lambda _name, data: events_received.append(data))

        body = {
            "events": [
                {
                    "type": "join",
                    "source": {"type": "group", "groupId": "C1111"},
                },
            ],
        }
        await ch.handle_webhook(body)
        assert len(events_received) == 1


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class TestDiagnostics:
    def test_missing_token(self) -> None:
        ch = LINEChannel(channel_access_token="")
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.CONFIG and "token" in i.message for i in issues)

    def test_missing_secret_warning(self) -> None:
        ch = LINEChannel(channel_access_token="tok")
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.CONFIG and i.severity == IssueSeverity.WARNING and "secret" in i.message for i in issues)

    def test_healthy_channel_no_config_errors(self) -> None:
        ch = LINEChannel(channel_access_token="tok", channel_secret="sec")
        issues = ch.collect_issues()
        config_errors = [i for i in issues if i.kind == IssueKind.CONFIG and i.severity == IssueSeverity.ERROR]
        assert len(config_errors) == 0

    def test_degraded_status_issue(self) -> None:
        ch = LINEChannel(channel_access_token="tok", channel_secret="sec")
        ch._status = ChannelStatus.DEGRADED
        ch.health.last_error = "API timeout"
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.RUNTIME and "degraded" in i.message.lower() for i in issues)


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_quick_replies_enabled(self) -> None:
        ch = LINEChannel(channel_access_token="tok")
        assert ch.capabilities.quick_replies is True

    def test_buttons_disabled(self) -> None:
        ch = LINEChannel(channel_access_token="tok")
        assert ch.capabilities.buttons is False

    def test_tool_summary_display(self) -> None:
        ch = LINEChannel(channel_access_token="tok")
        from app.channels.types import ToolSummaryDisplay

        assert ch.render_style.tool_summary_display == ToolSummaryDisplay.COMPACT


# ---------------------------------------------------------------------------
# Outbound — send path
# ---------------------------------------------------------------------------


def _mock_response(
    status_code: int = 200,
    json_data: dict[str, object] | None = None,
) -> httpx.Response:
    content = b"{}"
    if json_data is not None:
        import json as _json

        content = _json.dumps(json_data).encode()
    return httpx.Response(status_code, content=content)


def _outbound(
    content: str = "hello",
    recipient_id: str = "Uuser1",
    media: tuple[MediaAttachment, ...] = (),
    quick_replies: tuple[QuickReply, ...] = (),
) -> OutboundMessage:
    return OutboundMessage(
        channel="line",
        recipient_id=recipient_id,
        content=content,
        user_id="system",
        media=media,
        quick_replies=quick_replies,
    )


class TestSendEmptyRecipient:
    @pytest.mark.asyncio
    async def test_empty_recipient_returns_none(self) -> None:
        ch, _ = _make_channel()
        msg = _outbound(content="hello", recipient_id="")
        result = await ch.send(msg)
        assert result is None


class TestSendPush:
    @pytest.mark.asyncio
    async def test_push_returns_message_id(self) -> None:
        ch, _ = _make_channel()
        resp_data = {"sentMessages": [{"id": "mid-1", "quoteToken": "qt-out"}]}
        ch._api.push = AsyncMock(return_value=_mock_response(200, resp_data))

        result = await ch.send(_outbound(content="test msg"))
        assert result == "mid-1"
        assert ch._quote_tokens.get("Uuser1") == "qt-out"

    @pytest.mark.asyncio
    async def test_push_http_error_returns_none(self) -> None:
        ch, _ = _make_channel()
        ch._api.push = AsyncMock(return_value=_mock_response(429))

        result = await ch.send(_outbound(content="test"))
        assert result is None


class TestSendReplyFallback:
    @pytest.mark.asyncio
    async def test_uses_reply_token_when_valid(self) -> None:
        ch, _ = _make_channel()
        ch._reply_tokens["Uuser1"] = _ReplyToken("rt-valid")
        resp_data = {"sentMessages": [{"id": "mid-reply"}]}
        ch._api.reply = AsyncMock(return_value=_mock_response(200, resp_data))

        result = await ch.send(_outbound(content="reply test"))
        assert result == "mid-reply"
        assert "Uuser1" not in ch._reply_tokens

    @pytest.mark.asyncio
    async def test_falls_back_to_push_when_reply_fails(self) -> None:
        ch, _ = _make_channel()
        ch._reply_tokens["Uuser1"] = _ReplyToken("rt-fail")
        ch._api.reply = AsyncMock(return_value=_mock_response(400))
        ch._api.push = AsyncMock(
            return_value=_mock_response(200, {"sentMessages": [{"id": "mid-push"}]}),
        )

        result = await ch.send(_outbound(content="fallback test"))
        assert result == "mid-push"

    @pytest.mark.asyncio
    async def test_expired_reply_token_goes_to_push(self) -> None:
        ch, _ = _make_channel()
        token = _ReplyToken("rt-old")
        token.created_at -= 30.0
        ch._reply_tokens["Uuser1"] = token
        ch._api.push = AsyncMock(
            return_value=_mock_response(200, {"sentMessages": [{"id": "mid-push2"}]}),
        )

        result = await ch.send(_outbound(content="expired test"))
        assert result == "mid-push2"


class TestSendQuoteToken:
    @pytest.mark.asyncio
    async def test_quote_token_attached_to_first_text(self) -> None:
        ch, _ = _make_channel()
        ch._quote_tokens["Uuser1"] = "qt-ctx"

        captured_messages: list[dict[str, object]] = []

        async def _capture_push(
            to: str,
            messages: list[dict[str, object]],
        ) -> httpx.Response:
            captured_messages.extend(messages)
            return _mock_response(200, {"sentMessages": [{"id": "m1"}]})

        ch._api.push = AsyncMock(side_effect=_capture_push)
        await ch.send(_outbound(content="quoted"))

        assert len(captured_messages) > 0
        assert captured_messages[0].get("quoteToken") == "qt-ctx"


class TestSendException:
    @pytest.mark.asyncio
    async def test_exception_records_failure(self) -> None:
        ch, _ = _make_channel()
        ch._api.push = AsyncMock(side_effect=RuntimeError("connection reset"))

        result = await ch.send(_outbound(content="fail"))
        assert result is None


# ---------------------------------------------------------------------------
# Outbound — media messages
# ---------------------------------------------------------------------------


class TestBuildMediaMessage:
    def test_image_message(self) -> None:
        ma = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.jpg")
        result = LINEChannel._build_media_message(ma)
        assert result is not None
        assert result["type"] == "image"
        assert result["originalContentUrl"] == "https://example.com/img.jpg"

    def test_video_message(self) -> None:
        ma = MediaAttachment(media_type=MediaType.VIDEO, url="https://example.com/vid.mp4")
        result = LINEChannel._build_media_message(ma)
        assert result is not None
        assert result["type"] == "video"

    def test_audio_message(self) -> None:
        ma = MediaAttachment(media_type=MediaType.AUDIO, url="https://example.com/aud.m4a")
        result = LINEChannel._build_media_message(ma)
        assert result is not None
        assert result["type"] == "audio"
        assert result["duration"] == 60000

    def test_no_url_returns_none(self) -> None:
        ma = MediaAttachment(media_type=MediaType.IMAGE, url="")
        result = LINEChannel._build_media_message(ma)
        assert result is None

    def test_unsupported_type_returns_none(self) -> None:
        ma = MediaAttachment(media_type=MediaType.DOCUMENT, url="https://example.com/doc.pdf")
        result = LINEChannel._build_media_message(ma)
        assert result is None


class TestBuildOutboundQuickReply:
    @pytest.mark.asyncio
    async def test_quick_reply_attached(self) -> None:
        ch, _ = _make_channel()

        captured_messages: list[dict[str, object]] = []

        async def _capture_push(
            to: str,
            messages: list[dict[str, object]],
        ) -> httpx.Response:
            captured_messages.extend(messages)
            return _mock_response(200, {"sentMessages": [{"id": "m1"}]})

        ch._api.push = AsyncMock(side_effect=_capture_push)
        await ch.send(
            _outbound(
                content="pick one",
                quick_replies=(
                    QuickReply(label="Yes", text="yes"),
                    QuickReply(label="No", text="no"),
                ),
            )
        )
        assert len(captured_messages) > 0
        last_msg = captured_messages[-1]
        assert "quickReply" in last_msg


class TestSendWithMedia:
    @pytest.mark.asyncio
    async def test_media_included_in_outbound(self) -> None:
        ch, _ = _make_channel()

        captured_messages: list[dict[str, object]] = []

        async def _capture_push(
            to: str,
            messages: list[dict[str, object]],
        ) -> httpx.Response:
            captured_messages.extend(messages)
            return _mock_response(200, {"sentMessages": [{"id": "m1"}]})

        ch._api.push = AsyncMock(side_effect=_capture_push)
        await ch.send(
            _outbound(
                content="check this image",
                media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://cdn.example.com/photo.jpg"),),
            )
        )
        assert len(captured_messages) >= 2
        assert captured_messages[0].get("type") == "image"
        assert captured_messages[1].get("type") == "text"


# ---------------------------------------------------------------------------
# Typing indicator
# ---------------------------------------------------------------------------


class TestTypingIndicator:
    @pytest.mark.asyncio
    async def test_typing_for_dm(self) -> None:
        ch, _ = _make_channel()
        ch._api._http = AsyncMock()
        ch._api._http.post = AsyncMock(return_value=_mock_response(200))
        await ch.start_typing("Uuser1")
        ch._api._http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_typing_skipped_for_group(self) -> None:
        ch, _ = _make_channel()
        ch._api._http = AsyncMock()
        ch._api._http.post = AsyncMock(return_value=_mock_response(200))
        await ch.start_typing("C1234")
        ch._api._http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_typing_skipped_for_room(self) -> None:
        ch, _ = _make_channel()
        ch._api._http = AsyncMock()
        ch._api._http.post = AsyncMock(return_value=_mock_response(200))
        await ch.start_typing("R9999")
        ch._api._http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_typing_skipped_for_empty(self) -> None:
        ch, _ = _make_channel()
        ch._api._http = AsyncMock()
        ch._api._http.post = AsyncMock(return_value=_mock_response(200))
        await ch.start_typing("")
        ch._api._http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_typing_error_silenced(self) -> None:
        ch, _ = _make_channel()
        ch._api._http = AsyncMock()
        ch._api._http.post = AsyncMock(side_effect=RuntimeError("timeout"))
        await ch.start_typing("Uuser1")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        ch, _ = _make_channel()
        ch._api.health_check = AsyncMock(return_value=(True, ""))
        result = await ch.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        ch, _ = _make_channel()
        ch._api.health_check = AsyncMock(return_value=(False, "HTTP 500"))
        result = await ch.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self) -> None:
        ch, _ = _make_channel()
        ch._api.health_check = AsyncMock(side_effect=RuntimeError("network error"))
        result = await ch.health_check()
        assert result is False


# ---------------------------------------------------------------------------
# Lifecycle — start / stop
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_fetches_bot_info(self) -> None:
        ch, _ = _make_channel()
        ch._api.get_bot_info = AsyncMock(
            return_value={"userId": "Ubot1", "displayName": "TestBot"},
        )
        await ch.start()
        assert ch._bot_user_id == "Ubot1"
        assert ch._bot_display_name == "TestBot"

    @pytest.mark.asyncio
    async def test_start_no_token_skips(self) -> None:
        ch = LINEChannel(channel_access_token="")
        ch._api.get_bot_info = AsyncMock()
        await ch.start()
        ch._api.get_bot_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_closes_http(self) -> None:
        ch, _ = _make_channel()
        ch._api.close = AsyncMock()
        await ch.stop()
        ch._api.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_bot_info_failure_graceful(self) -> None:
        ch, _ = _make_channel()
        ch._api.get_bot_info = AsyncMock(side_effect=RuntimeError("dns fail"))
        await ch.start()
        assert ch._bot_user_id == ""


# ---------------------------------------------------------------------------
# Mention — displayName index-based detection
# ---------------------------------------------------------------------------


class TestMentionDisplayNameIndex:
    @pytest.mark.asyncio
    async def test_display_name_in_mentionee_text(self) -> None:
        ch, received = _make_channel()
        ch._bot_display_name = "MyBot"
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="@MyBot do something",
            mention={
                "mentionees": [
                    {"index": 0, "length": 6, "userId": "Uother"},
                ],
            },
        )
        await ch.handle_webhook(body)
        assert len(received) == 1
        assert received[0].mentioned is True


class TestMentionStripByUserId:
    @pytest.mark.asyncio
    async def test_strip_by_user_id(self) -> None:
        ch, received = _make_channel()
        ch._bot_user_id = "Ubot"
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="@bot help me",
            mention={
                "mentionees": [{"userId": "Ubot", "index": 0, "length": 4}],
            },
        )
        await ch.handle_webhook(body)
        assert received[0].content == "help me"


class TestMentionStripByDisplayNameIndex:
    @pytest.mark.asyncio
    async def test_strip_by_display_name_index(self) -> None:
        ch, received = _make_channel()
        ch._bot_display_name = "AI Bot"
        body = _make_event(
            source_type="group",
            group_id="C1",
            text="@AI Bot what time",
            mention={
                "mentionees": [{"index": 0, "length": 7, "userId": "Uother"}],
            },
        )
        await ch.handle_webhook(body)
        assert received[0].content == "what time"


# ---------------------------------------------------------------------------
# Parse response / extract helpers
# ---------------------------------------------------------------------------


class TestParseHelpers:
    def test_extract_message_id_from_valid(self) -> None:
        data: dict[str, object] = {"sentMessages": [{"id": "abc123"}]}
        assert LINEChannel._extract_message_id_from(data) == "abc123"

    def test_extract_message_id_from_empty(self) -> None:
        data: dict[str, object] = {"sentMessages": []}
        assert LINEChannel._extract_message_id_from(data) is None

    def test_extract_message_id_from_no_key(self) -> None:
        data: dict[str, object] = {}
        assert LINEChannel._extract_message_id_from(data) is None

    def test_store_quote_token_valid(self) -> None:
        ch, _ = _make_channel()
        data: dict[str, object] = {"sentMessages": [{"quoteToken": "qt-1"}]}
        ch._store_quote_token("Uuser", data)
        assert ch._quote_tokens["Uuser"] == "qt-1"

    def test_store_quote_token_empty(self) -> None:
        ch, _ = _make_channel()
        data: dict[str, object] = {"sentMessages": [{"quoteToken": ""}]}
        ch._store_quote_token("Uuser", data)
        assert "Uuser" not in ch._quote_tokens


# ---------------------------------------------------------------------------
# LineClient (api.py) direct tests
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock  # noqa: E402

from app.channels.providers.line.api import LineClient  # noqa: E402


def _mock_line_client() -> LineClient:
    """Create a LineClient with a mocked httpx.AsyncClient."""
    client = LineClient("test-token")
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.is_closed = False
    client._http = mock_http
    return client


class TestLineClient:
    @pytest.mark.asyncio
    async def test_get_bot_info_success(self) -> None:
        client = _mock_line_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"userId": "Ubot", "displayName": "Bot"}
        client._http.get.return_value = resp

        result = await client.get_bot_info()
        assert result == {"userId": "Ubot", "displayName": "Bot"}

    @pytest.mark.asyncio
    async def test_get_bot_info_failure(self) -> None:
        client = _mock_line_client()
        resp = MagicMock()
        resp.status_code = 401
        client._http.get.return_value = resp

        result = await client.get_bot_info()
        assert result == {}

    @pytest.mark.asyncio
    async def test_health_check_ok(self) -> None:
        client = _mock_line_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.get.return_value = resp

        ok, msg = await client.health_check()
        assert ok is True
        assert msg == ""

    @pytest.mark.asyncio
    async def test_health_check_fail(self) -> None:
        client = _mock_line_client()
        resp = MagicMock()
        resp.status_code = 500
        client._http.get.return_value = resp

        ok, msg = await client.health_check()
        assert ok is False
        assert "500" in msg

    @pytest.mark.asyncio
    async def test_reply(self) -> None:
        client = _mock_line_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.reply("token-1", [{"type": "text", "text": "hi"}])
        assert result.status_code == 200
        client._http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_push(self) -> None:
        client = _mock_line_client()
        resp = MagicMock()
        resp.status_code = 200
        client._http.post.return_value = resp

        result = await client.push("Uuser1", [{"type": "text", "text": "hi"}])
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_start_loading_user_chat(self) -> None:
        client = _mock_line_client()
        await client.start_loading("Uuser1")
        client._http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_loading_group_skipped(self) -> None:
        client = _mock_line_client()
        await client.start_loading("C1234")
        client._http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_loading_empty_skipped(self) -> None:
        client = _mock_line_client()
        await client.start_loading("")
        client._http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        client = _mock_line_client()
        await client.close()
        client._http.aclose.assert_called_once()
