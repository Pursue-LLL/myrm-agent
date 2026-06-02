"""QQChannel contract compliance + WebSocket + send + media + lifecycle tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelSendError,
)
from app.channels.providers.qq import QQChannel
from app.channels.providers.qq.helpers import (
    build_media_upload_url,
    build_message_url,
    is_group_event,
    is_supported_event,
    parse_attachments,
    parse_sender_id,
    qq_file_type,
    sanitize_urls,
)
from app.channels.types import (
    ChannelStatus,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    ToolSummaryDisplay,
)

from .channel_test_base import ChannelTestBase


def _make_channel(*, sandbox: bool = False) -> QQChannel:
    ch = QQChannel(app_id="test_app", client_secret="test_secret", sandbox=sandbox)
    ch._api._access_token = "mock_token"
    ch._api._token_expires_at = 9999999999.0
    return ch


def _ok_json(body: dict[str, object] | None = None) -> httpx.Response:
    return httpx.Response(200, json=body or {})


def _err_json(status: int = 400) -> httpx.Response:
    return httpx.Response(status, json={"code": status, "message": "error"})


# ── Contract Compliance ──────────────────────────────────────────────


class TestQQChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return QQChannel(app_id="test", client_secret="secret")


# ── Helpers Tests ────────────────────────────────────────────────────


class TestQQHelpers:
    """Tests for pure helper functions in qq/helpers.py."""

    def test_is_supported_event_group_at(self) -> None:
        assert is_supported_event("GROUP_AT_MESSAGE_CREATE") is True

    def test_is_supported_event_at(self) -> None:
        assert is_supported_event("AT_MESSAGE_CREATE") is True

    def test_is_supported_event_c2c(self) -> None:
        assert is_supported_event("C2C_MESSAGE_CREATE") is True

    def test_is_supported_event_direct(self) -> None:
        assert is_supported_event("DIRECT_MESSAGE_CREATE") is True

    def test_is_supported_event_unknown(self) -> None:
        assert is_supported_event("UNKNOWN_EVENT") is False

    def test_is_group_event_group_at(self) -> None:
        assert is_group_event("GROUP_AT_MESSAGE_CREATE") is True

    def test_is_group_event_at(self) -> None:
        assert is_group_event("AT_MESSAGE_CREATE") is True

    def test_is_group_event_c2c(self) -> None:
        assert is_group_event("C2C_MESSAGE_CREATE") is False

    def test_is_group_event_direct(self) -> None:
        assert is_group_event("DIRECT_MESSAGE_CREATE") is False

    def test_parse_sender_id_member_openid(self) -> None:
        assert parse_sender_id({"member_openid": "m123"}) == "m123"

    def test_parse_sender_id_user_openid(self) -> None:
        assert parse_sender_id({"user_openid": "u456"}) == "u456"

    def test_parse_sender_id_id(self) -> None:
        assert parse_sender_id({"id": "789"}) == "789"

    def test_parse_sender_id_priority(self) -> None:
        assert parse_sender_id({"member_openid": "m1", "user_openid": "u2", "id": "3"}) == "m1"

    def test_parse_sender_id_empty(self) -> None:
        assert parse_sender_id({}) == ""

    def test_parse_attachments_image(self) -> None:
        raw = [{"content_type": "image/png", "url": "https://img.qq.com/1.png", "filename": "1.png"}]
        result = parse_attachments(raw)
        assert len(result) == 1
        assert result[0].media_type == MediaType.IMAGE
        assert result[0].url == "https://img.qq.com/1.png"

    def test_parse_attachments_audio(self) -> None:
        raw = [{"content_type": "audio/mpeg", "url": "https://a.qq.com/1.mp3", "filename": "1.mp3"}]
        result = parse_attachments(raw)
        assert result[0].media_type == MediaType.AUDIO

    def test_parse_attachments_video(self) -> None:
        raw = [{"content_type": "video/mp4", "url": "https://v.qq.com/1.mp4", "filename": "1.mp4"}]
        result = parse_attachments(raw)
        assert result[0].media_type == MediaType.VIDEO

    def test_parse_attachments_document(self) -> None:
        raw = [{"content_type": "application/pdf", "url": "https://d.qq.com/1.pdf", "filename": "1.pdf"}]
        result = parse_attachments(raw)
        assert result[0].media_type == MediaType.DOCUMENT

    def test_parse_attachments_empty(self) -> None:
        assert parse_attachments([]) == []

    def test_qq_file_type_image(self) -> None:
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.qq.com/1.png")
        assert qq_file_type(att) == 1

    def test_qq_file_type_video(self) -> None:
        att = MediaAttachment(media_type=MediaType.VIDEO, url="https://v.qq.com/1.mp4")
        assert qq_file_type(att) == 2

    def test_qq_file_type_audio_as_file(self) -> None:
        att = MediaAttachment(media_type=MediaType.AUDIO, url="https://a.qq.com/1.mp3")
        assert qq_file_type(att) == 4

    def test_qq_file_type_document(self) -> None:
        att = MediaAttachment(media_type=MediaType.DOCUMENT, url="https://d.qq.com/1.pdf")
        assert qq_file_type(att) == 4

    def test_sanitize_urls_replaces_domain_dots(self) -> None:
        text = "Visit https://example.com/path for details"
        result = sanitize_urls(text)
        assert "example\u3002com" in result
        assert "/path" in result

    def test_sanitize_urls_preserves_non_url_text(self) -> None:
        text = "Hello world, no URLs here."
        assert sanitize_urls(text) == text

    def test_sanitize_urls_preserves_path(self) -> None:
        text = "See https://api.example.com/v2/data?key=val"
        result = sanitize_urls(text)
        assert "api\u3002example\u3002com" in result
        assert "/v2/data?key=val" in result

    def test_sanitize_urls_multiple_urls(self) -> None:
        text = "Check https://a.com and https://b.org/page"
        result = sanitize_urls(text)
        assert "a\u3002com" in result
        assert "b\u3002org" in result

    def test_sanitize_urls_http(self) -> None:
        text = "Visit http://example.com"
        result = sanitize_urls(text)
        assert "http://example\u3002com" in result

    def test_build_message_url_group(self) -> None:
        url = build_message_url("https://api.sgroup.qq.com", "G123", "group")
        assert url == "https://api.sgroup.qq.com/v2/groups/G123/messages"

    def test_build_message_url_c2c(self) -> None:
        url = build_message_url("https://api.sgroup.qq.com", "U456", "c2c")
        assert url == "https://api.sgroup.qq.com/v2/users/U456/messages"

    def test_build_message_url_channel(self) -> None:
        url = build_message_url("https://api.sgroup.qq.com", "CH789", "channel")
        assert url == "https://api.sgroup.qq.com/channels/CH789/messages"

    def test_build_media_upload_url_group(self) -> None:
        url = build_media_upload_url("https://api.sgroup.qq.com", "G123", "group")
        assert url == "https://api.sgroup.qq.com/v2/groups/G123/files"

    def test_build_media_upload_url_c2c(self) -> None:
        url = build_media_upload_url("https://api.sgroup.qq.com", "U456", "c2c")
        assert url == "https://api.sgroup.qq.com/v2/users/U456/files"


# ── Capabilities & Config ────────────────────────────────────────────


class TestQQCapabilities:
    def test_name(self) -> None:
        assert QQChannel.name == "qq"

    def test_capabilities_text_and_markdown(self) -> None:
        assert QQChannel.capabilities.text is True
        assert QQChannel.capabilities.markdown is True

    def test_capabilities_media(self) -> None:
        assert QQChannel.capabilities.media is True
        assert QQChannel.capabilities.file_upload is True

    def test_capabilities_no_interactive(self) -> None:
        assert QQChannel.capabilities.buttons is False
        assert QQChannel.capabilities.quick_replies is False
        assert QQChannel.capabilities.select_menus is False

    def test_capabilities_no_edit_delete(self) -> None:
        assert QQChannel.capabilities.edit is False
        assert QQChannel.capabilities.delete is False
        assert QQChannel.capabilities.reactions is False

    def test_capabilities_typing(self) -> None:
        assert QQChannel.capabilities.typing_indicator is True

    def test_render_style_compact(self) -> None:
        assert QQChannel.render_style.tool_summary_display == ToolSummaryDisplay.COMPACT
        assert QQChannel.render_style.format == "markdown"

    def test_sandbox_api_base(self) -> None:
        ch = QQChannel(app_id="a", client_secret="s", sandbox=True)
        assert "sandbox" in ch._api_base

    def test_production_api_base(self) -> None:
        ch = QQChannel(app_id="a", client_secret="s", sandbox=False)
        assert "sandbox" not in ch._api_base


# ── Lifecycle ────────────────────────────────────────────────────────


class TestQQLifecycle:
    @pytest.mark.asyncio
    async def test_start_no_credentials(self) -> None:
        ch = QQChannel(app_id="", client_secret="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_token_failure(self) -> None:
        ch = QQChannel(app_id="app", client_secret="secret")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json(401)):
            await ch.start()
        assert ch._status == ChannelStatus.ERROR
        await ch._api._http.aclose()

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = QQChannel(app_id="app", client_secret="secret")
        token_resp = _ok_json({"access_token": "tok", "expires_in": 7200})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=token_resp):
            await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._ws_task is not None
        ch._ws_task.cancel()
        try:
            await ch._ws_task
        except (asyncio.CancelledError, Exception):
            pass
        await ch._api._http.aclose()

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_cancels_ws_task(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING

        async def _forever() -> None:
            await asyncio.sleep(999)

        ch._ws_task = asyncio.create_task(_forever())
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_health_check_ok(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._api._http, "get", new_callable=AsyncMock, return_value=httpx.Response(200)):
            assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_not_running(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._api._http, "get", new_callable=AsyncMock, side_effect=Exception("net")):
            assert await ch.health_check() is False


# ── Token Management ─────────────────────────────────────────────────


class TestQQToken:
    @pytest.mark.asyncio
    async def test_refresh_token_success(self) -> None:
        ch = QQChannel(app_id="app", client_secret="secret")
        resp = _ok_json({"access_token": "new_tok", "expires_in": 7200})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp):
            await ch._api.refresh_token()
        assert ch._api._access_token == "new_tok"
        assert ch._api._token_expires_at > 0
        await ch._api._http.aclose()

    @pytest.mark.asyncio
    async def test_refresh_token_failure(self) -> None:
        ch = QQChannel(app_id="app", client_secret="secret")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json(401)):
            with pytest.raises(ChannelAuthError):
                await ch._api.refresh_token()
        await ch._api._http.aclose()

    @pytest.mark.asyncio
    async def test_ensure_token_lock_prevents_concurrent_refresh(self) -> None:
        ch = QQChannel(app_id="app", client_secret="secret")
        ch._api._token_expires_at = 0.0
        call_count = 0

        async def _mock_refresh() -> None:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            ch._api._access_token = "refreshed"
            ch._api._token_expires_at = 9999999999.0

        with patch.object(ch._api, "refresh_token", side_effect=_mock_refresh):
            await asyncio.gather(ch._api.ensure_token(), ch._api.ensure_token(), ch._api.ensure_token())

        assert call_count == 1
        await ch._api._http.aclose()

    def test_auth_headers(self) -> None:
        ch = _make_channel()
        headers = ch._api.auth_headers()
        assert headers["Authorization"] == "QQBot mock_token"
        assert headers["Content-Type"] == "application/json"


# ── Send ─────────────────────────────────────────────────────────────


class TestQQSend:
    @pytest.mark.asyncio
    async def test_send_text_group(self) -> None:
        ch = _make_channel()
        ch._chat_types["G123"] = "group"
        ch._last_msg_ids["G123"] = "mid_1"
        msg = OutboundMessage(channel="qq", recipient_id="G123", content="Hello", user_id="U")
        resp = _ok_json({"id": "sent_1"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp) as mock_post:
            result = await ch.send(msg)
        assert result == "sent_1"
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload["msg_type"] == 0
        assert "msg_seq" in payload
        assert "msg_id" in payload

    @pytest.mark.asyncio
    async def test_send_text_group_url_sanitized(self) -> None:
        ch = _make_channel()
        ch._chat_types["G123"] = "group"
        ch._last_msg_ids["G123"] = "mid_1"
        msg = OutboundMessage(
            channel="qq",
            recipient_id="G123",
            content="Visit https://example.com for details",
            user_id="U",
        )
        resp = _ok_json({"id": "sent_1"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp) as mock_post:
            await ch.send(msg)
        payload = mock_post.call_args.kwargs.get("json", {})
        assert "\u3002" in payload["content"]

    @pytest.mark.asyncio
    async def test_send_text_c2c_no_url_sanitize(self) -> None:
        ch = _make_channel()
        ch._chat_types["U456"] = "c2c"
        ch._last_msg_ids["U456"] = "mid_2"
        msg = OutboundMessage(
            channel="qq",
            recipient_id="U456",
            content="Visit https://example.com",
            user_id="U",
        )
        resp = _ok_json({"id": "sent_2"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp) as mock_post:
            await ch.send(msg)
        payload = mock_post.call_args.kwargs.get("json", {})
        assert "\u3002" not in payload["content"]

    @pytest.mark.asyncio
    async def test_send_text_failure(self) -> None:
        ch = _make_channel()
        ch._chat_types["G123"] = "group"
        msg = OutboundMessage(channel="qq", recipient_id="G123", content="Hi", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=Exception("net")):
            with pytest.raises(ChannelSendError):
                await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_text_http_error(self) -> None:
        ch = _make_channel()
        ch._chat_types["G123"] = "group"
        msg = OutboundMessage(channel="qq", recipient_id="G123", content="Hi", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json(400)):
            result = await ch.send(msg)
        assert result is None


# ── Media Upload ─────────────────────────────────────────────────────


class TestQQMedia:
    @pytest.mark.asyncio
    async def test_send_media_2step_success(self) -> None:
        ch = _make_channel()
        ch._chat_types["G123"] = "group"
        ch._last_msg_ids["G123"] = "mid_1"
        attachment = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.qq.com/1.png")
        msg = OutboundMessage(
            channel="qq",
            recipient_id="G123",
            content="",
            user_id="U",
            media=(attachment,),
        )
        upload_resp = _ok_json({"file_info": "fi_abc"})
        send_resp = _ok_json({"id": "media_1"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=[upload_resp, send_resp]):
            result = await ch.send(msg)
        assert result == "media_1"

    @pytest.mark.asyncio
    async def test_send_media_upload_failure(self) -> None:
        ch = _make_channel()
        ch._chat_types["G123"] = "group"
        attachment = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.qq.com/1.png")
        msg = OutboundMessage(
            channel="qq",
            recipient_id="G123",
            content="",
            user_id="U",
            media=(attachment,),
        )
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json(400)):
            result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_media_no_url(self) -> None:
        ch = _make_channel()
        ch._chat_types["G123"] = "group"
        attachment = MediaAttachment(media_type=MediaType.IMAGE)
        msg = OutboundMessage(
            channel="qq",
            recipient_id="G123",
            content="",
            user_id="U",
            media=(attachment,),
        )
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_media_no_file_info(self) -> None:
        ch = _make_channel()
        ch._chat_types["G123"] = "group"
        attachment = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.qq.com/1.png")
        msg = OutboundMessage(
            channel="qq",
            recipient_id="G123",
            content="",
            user_id="U",
            media=(attachment,),
        )
        resp = _ok_json({})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp):
            result = await ch.send(msg)
        assert result is None


# ── msg_seq ──────────────────────────────────────────────────────────


class TestQQMsgSeq:
    def test_next_seq_increments(self) -> None:
        ch = _make_channel()
        ch._msg_seq_counters["chat1"] = 1
        assert ch._next_seq("chat1") == 1
        assert ch._next_seq("chat1") == 2
        assert ch._next_seq("chat1") == 3

    def test_next_seq_default(self) -> None:
        ch = _make_channel()
        assert ch._next_seq("new_chat") == 1

    def test_msg_seq_reset_on_new_inbound(self) -> None:
        ch = _make_channel()
        ch._msg_seq_counters["chat1"] = 5
        data: dict[str, object] = {
            "author": {"member_openid": "sender1"},
            "content": "hello",
            "id": "msg_new",
            "group_openid": "chat1",
        }
        ch._parse_event("GROUP_AT_MESSAGE_CREATE", data)
        assert ch._msg_seq_counters["chat1"] == 1


# ── Typing Indicator ─────────────────────────────────────────────────


class TestQQTyping:
    @pytest.mark.asyncio
    async def test_start_typing_sends_input_notify(self) -> None:
        ch = _make_channel()
        ch._last_msg_ids["G123"] = "mid_1"
        ch._chat_types["G123"] = "group"
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.start_typing("G123")
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload["msg_type"] == 6

    @pytest.mark.asyncio
    async def test_start_typing_no_msg_id(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock) as mock_post:
            await ch.start_typing("G123")
        mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_typing_exception_ignored(self) -> None:
        ch = _make_channel()
        ch._last_msg_ids["G123"] = "mid_1"
        ch._chat_types["G123"] = "group"
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=Exception("net")):
            await ch.start_typing("G123")


# ── Event Parsing ────────────────────────────────────────────────────


class TestQQEventParsing:
    def test_parse_group_at_message(self) -> None:
        ch = _make_channel()
        data: dict[str, object] = {
            "author": {"member_openid": "sender1"},
            "content": " hello bot",
            "id": "msg_1",
            "group_openid": "grp_1",
        }
        msg = ch._parse_event("GROUP_AT_MESSAGE_CREATE", data)
        assert msg is not None
        assert msg.sender_id == "sender1"
        assert msg.content == "hello bot"
        assert msg.is_group is True
        assert msg.mentioned is True
        assert msg.chat_id == "grp_1"

    def test_parse_c2c_message(self) -> None:
        ch = _make_channel()
        data: dict[str, object] = {
            "author": {"user_openid": "user1"},
            "content": "dm message",
            "id": "msg_2",
            "group_openid": "",
            "channel_id": "",
        }
        msg = ch._parse_event("C2C_MESSAGE_CREATE", data)
        assert msg is not None
        assert msg.is_group is False
        assert msg.mentioned is False

    def test_parse_event_no_author(self) -> None:
        ch = _make_channel()
        data: dict[str, object] = {"content": "no author", "id": "msg_3"}
        msg = ch._parse_event("GROUP_AT_MESSAGE_CREATE", data)
        assert msg is None

    def test_parse_event_empty_content_no_media(self) -> None:
        ch = _make_channel()
        data: dict[str, object] = {
            "author": {"member_openid": "sender1"},
            "content": "",
            "id": "msg_4",
            "group_openid": "grp_1",
        }
        msg = ch._parse_event("GROUP_AT_MESSAGE_CREATE", data)
        assert msg is None

    def test_parse_event_with_attachments(self) -> None:
        ch = _make_channel()
        data: dict[str, object] = {
            "author": {"member_openid": "sender1"},
            "content": "",
            "id": "msg_5",
            "group_openid": "grp_1",
            "attachments": [{"content_type": "image/png", "url": "https://img.qq.com/1.png", "filename": "1.png"}],
        }
        msg = ch._parse_event("GROUP_AT_MESSAGE_CREATE", data)
        assert msg is not None
        assert len(msg.media) == 1

    def test_parse_event_stores_chat_state(self) -> None:
        ch = _make_channel()
        data: dict[str, object] = {
            "author": {"member_openid": "sender1"},
            "content": "hello",
            "id": "msg_6",
            "group_openid": "grp_1",
        }
        ch._parse_event("GROUP_AT_MESSAGE_CREATE", data)
        assert ch._chat_types["grp_1"] == "group"
        assert ch._last_msg_ids["grp_1"] == "msg_6"
        assert ch._msg_seq_counters["grp_1"] == 1


# ── Webhook ──────────────────────────────────────────────────────────


class TestQQWebhook:
    @pytest.mark.asyncio
    async def test_webhook_validation(self) -> None:
        ch = _make_channel()
        body: dict[str, object] = {
            "op": 13,
            "d": {"plain_token": "abc", "event_ts": "123"},
        }
        result = await ch.handle_webhook(body)
        assert result is not None
        assert result["op"] == 13
        d = result["d"]
        assert isinstance(d, dict)
        assert d["plain_token"] == "abc"

    @pytest.mark.asyncio
    async def test_webhook_message_event(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        body: dict[str, object] = {
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "author": {"member_openid": "sender1"},
                "content": "hello",
                "id": "msg_w1",
                "group_openid": "grp_1",
            },
        }
        result = await ch.handle_webhook(body)
        assert result is None
        assert len(emitted) == 1

    @pytest.mark.asyncio
    async def test_webhook_unsupported_event(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        body: dict[str, object] = {"t": "UNKNOWN_EVENT", "d": {}}
        await ch.handle_webhook(body)
        ch._emit_inbound.assert_not_called()


# ── WebSocket Message Handling ───────────────────────────────────────


class TestQQWebSocketHandling:
    @pytest.mark.asyncio
    async def test_handle_ws_ready(self) -> None:
        ch = _make_channel()
        msg: dict[str, object] = {
            "op": 0,
            "s": 1,
            "t": "READY",
            "d": {"session_id": "sess_abc"},
        }
        await ch._handle_ws_message(msg)
        assert ch._session_id == "sess_abc"
        assert ch._last_seq == 1

    @pytest.mark.asyncio
    async def test_handle_ws_resumed(self) -> None:
        ch = _make_channel()
        msg: dict[str, object] = {"op": 0, "s": 2, "t": "RESUMED", "d": {}}
        await ch._handle_ws_message(msg)
        assert ch._last_seq == 2

    @pytest.mark.asyncio
    async def test_handle_ws_dispatch_event(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        msg: dict[str, object] = {
            "op": 0,
            "s": 3,
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "author": {"member_openid": "sender1"},
                "content": "ws hello",
                "id": "ws_msg_1",
                "group_openid": "grp_ws",
            },
        }
        await ch._handle_ws_message(msg)
        assert len(emitted) == 1
        assert ch._last_seq == 3

    @pytest.mark.asyncio
    async def test_handle_ws_reconnect_op7(self) -> None:
        ch = _make_channel()
        with pytest.raises(RuntimeError, match="reconnect"):
            await ch._handle_ws_message({"op": 7})

    @pytest.mark.asyncio
    async def test_handle_ws_invalid_session_op9(self) -> None:
        ch = _make_channel()
        ch._session_id = "old_session"
        ch._last_seq = 5
        with pytest.raises(RuntimeError, match="Invalid session"):
            await ch._handle_ws_message({"op": 9})
        assert ch._session_id == ""
        assert ch._last_seq is None


# ── Diagnostics ──────────────────────────────────────────────────────


class TestQQDiagnostics:
    def test_collect_issues_no_credentials(self) -> None:
        ch = QQChannel(app_id="", client_secret="")
        issues = ch.collect_issues()
        assert len(issues) >= 1
        assert any("App ID" in i.message for i in issues)
        assert any("Client Secret" in i.message for i in issues)

    def test_collect_issues_missing_app_id(self) -> None:
        ch = QQChannel(app_id="", client_secret="secret")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "App ID" in issues[0].message
        assert "Client Secret" not in issues[0].message

    def test_collect_issues_ok(self) -> None:
        ch = _make_channel()
        issues = ch.collect_issues()
        assert len(issues) == 0

    def test_collect_issues_runtime_error(self) -> None:
        ch = _make_channel()
        ch.health.last_error = "Connection refused"
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "Connection refused" in issues[0].message
