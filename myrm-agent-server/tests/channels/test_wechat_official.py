"""Tests for WeChatOfficialChannel (公众号 API)."""

from __future__ import annotations

import hashlib
import time
from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import (
    ChannelAuthError,
)
from app.channels.providers.wechat.official_channel import (
    _MAX_TEXT_LENGTH,
    WeChatOfficialChannel,
)
from app.channels.types import (
    ChannelStatus,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase


class TestWeChatOfficialContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return WeChatOfficialChannel(app_id="test_id", app_secret="test_secret", token="test_token")


def _make_channel() -> WeChatOfficialChannel:
    ch = WeChatOfficialChannel(app_id="test_id", app_secret="test_secret", token="test_token")
    ch._access_token = "fake_token"
    ch._token_expires_at = time.monotonic() + 7200
    ch._status = ChannelStatus.RUNNING
    return ch


def _xml_msg(msg_type: str, content: str = "", pic_url: str = "", recognition: str = "") -> str:
    parts = [
        "<xml>",
        f"<MsgType><![CDATA[{msg_type}]]></MsgType>",
        "<FromUserName><![CDATA[user123]]></FromUserName>",
        "<ToUserName><![CDATA[bot456]]></ToUserName>",
        "<MsgId>12345</MsgId>",
    ]
    if content:
        parts.append(f"<Content><![CDATA[{content}]]></Content>")
    if pic_url:
        parts.append(f"<PicUrl><![CDATA[{pic_url}]]></PicUrl>")
    if recognition:
        parts.append(f"<Recognition><![CDATA[{recognition}]]></Recognition>")
    parts.append("</xml>")
    return "".join(parts)


# ── Capabilities ───────────────────────────────────────────────────────


class TestCapabilities:
    def test_name(self) -> None:
        ch = _make_channel()
        assert ch.name == "wechat_official"

    def test_capabilities_flags(self) -> None:
        ch = _make_channel()
        assert ch.capabilities.text is True
        assert ch.capabilities.media is True
        assert ch.capabilities.voice_message is True
        assert ch.capabilities.typing_indicator is False
        assert ch.capabilities.max_text_length == _MAX_TEXT_LENGTH


# ── Lifecycle ──────────────────────────────────────────────────────────


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = WeChatOfficialChannel(app_id="id", app_secret="secret")
        mock_resp = httpx.Response(
            200,
            json={"access_token": "tok123", "expires_in": 7200},
            request=httpx.Request("GET", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)
        await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._access_token == "tok123"

    @pytest.mark.asyncio
    async def test_start_no_credentials(self) -> None:
        ch = WeChatOfficialChannel(app_id="", app_secret="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_token_failure(self) -> None:
        ch = WeChatOfficialChannel(app_id="id", app_secret="secret")
        mock_resp = httpx.Response(
            401,
            request=httpx.Request("GET", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)
        ch._http.aclose = AsyncMock()
        await ch.start()
        assert ch._status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._http = AsyncMock()
        ch._http.aclose = AsyncMock()
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        ch._http.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_running(self) -> None:
        ch = _make_channel()
        ch._http = AsyncMock()
        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_stopped(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_token_expired(self) -> None:
        ch = _make_channel()
        ch._token_expires_at = 0.0
        mock_resp = httpx.Response(
            401,
            request=httpx.Request("GET", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)
        assert await ch.health_check() is False


# ── Verify URL ─────────────────────────────────────────────────────────


class TestVerifyUrl:
    def test_valid_signature(self) -> None:
        import time

        ch = _make_channel()
        timestamp = str(int(time.time()))
        nonce = "nonce123"
        sort_list = sorted(["test_token", timestamp, nonce])
        expected = hashlib.sha1("".join(sort_list).encode("utf-8")).hexdigest()
        assert ch.verify_url(expected, timestamp, nonce) is True

    def test_invalid_signature(self) -> None:
        ch = _make_channel()
        assert ch.verify_url("invalid", "123", "nonce") is False


# ── Handle Callback (Inbound) ─────────────────────────────────────────


class TestHandleCallback:
    @pytest.mark.asyncio
    async def test_text_message(self) -> None:
        ch = _make_channel()
        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda m: captured.append(m))

        result = await ch.handle_callback(_xml_msg("text", content="hello"))
        assert result == "success"
        assert len(captured) == 1
        msg = captured[0]
        assert msg.content == "hello"
        assert msg.sender_id == "user123"

    @pytest.mark.asyncio
    async def test_image_message(self) -> None:
        ch = _make_channel()
        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda m: captured.append(m))

        result = await ch.handle_callback(_xml_msg("image", pic_url="https://img.example.com/1.jpg"))
        assert result == "success"
        assert len(captured) == 1
        msg = captured[0]
        assert msg.media[0].media_type == MediaType.IMAGE
        assert msg.media[0].url == "https://img.example.com/1.jpg"

    @pytest.mark.asyncio
    async def test_voice_with_recognition(self) -> None:
        ch = _make_channel()
        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda m: captured.append(m))

        result = await ch.handle_callback(_xml_msg("voice", recognition="hello world"))
        assert result == "success"
        assert captured[0].content == "hello world"

    @pytest.mark.asyncio
    async def test_voice_without_recognition(self) -> None:
        ch = _make_channel()
        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda m: captured.append(m))

        result = await ch.handle_callback(_xml_msg("voice"))
        assert result == "success"
        assert captured[0].media[0].media_type == MediaType.AUDIO

    @pytest.mark.asyncio
    async def test_video_message(self) -> None:
        ch = _make_channel()
        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda m: captured.append(m))

        result = await ch.handle_callback(_xml_msg("video"))
        assert result == "success"
        assert captured[0].media[0].media_type == MediaType.VIDEO

    @pytest.mark.asyncio
    async def test_shortvideo_message(self) -> None:
        ch = _make_channel()
        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda m: captured.append(m))

        result = await ch.handle_callback(_xml_msg("shortvideo"))
        assert result == "success"
        assert captured[0].media[0].media_type == MediaType.VIDEO

    @pytest.mark.asyncio
    async def test_event_message_ignored(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()

        result = await ch.handle_callback(_xml_msg("event"))
        assert result == "success"
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_xml(self) -> None:
        ch = _make_channel()
        result = await ch.handle_callback("not xml at all")
        assert result is None

    @pytest.mark.asyncio
    async def test_bytes_input(self) -> None:
        ch = _make_channel()
        captured: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda m: captured.append(m))

        result = await ch.handle_callback(_xml_msg("text", content="hi").encode("utf-8"))
        assert result == "success"
        assert captured[0].content == "hi"

    @pytest.mark.asyncio
    async def test_empty_content_ignored(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()

        xml = "<xml><MsgType><![CDATA[text]]></MsgType><FromUserName><![CDATA[u]]></FromUserName><Content></Content></xml>"
        result = await ch.handle_callback(xml)
        assert result == "success"
        ch._emit_inbound.assert_not_called()


# ── Send ───────────────────────────────────────────────────────────────


class TestSend:
    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        ch = _make_channel()
        mock_resp = httpx.Response(
            200,
            json={"errcode": 0},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")
        await ch.send(msg)
        ch._http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_http_error(self) -> None:
        from app.channels.core.exceptions import ChannelSendError

        ch = _make_channel()
        mock_resp = httpx.Response(
            500,
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")
        with pytest.raises(ChannelSendError, match="HTTP 500"):
            await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_non_rate_limit_error(self) -> None:
        from app.channels.core.exceptions import ChannelSendError

        ch = _make_channel()
        mock_resp = httpx.Response(
            200,
            json={"errcode": 48001, "errmsg": "api unauthorized"},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")
        with pytest.raises(ChannelSendError, match="errcode=48001"):
            await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_token_expired_auto_retry(self) -> None:
        ch = _make_channel()
        expired_resp = httpx.Response(
            200,
            json={"errcode": 42001, "errmsg": "access_token expired"},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        ok_resp = httpx.Response(
            200,
            json={"errcode": 0, "errmsg": "ok"},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        token_resp = httpx.Response(
            200,
            json={"access_token": "new_token", "expires_in": 7200},
            request=httpx.Request("GET", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(side_effect=[expired_resp, ok_resp])
        ch._http.get = AsyncMock(return_value=token_resp)

        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="hello", user_id="u1")
        await ch.send(msg)
        assert ch._http.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_media_image(self) -> None:
        from unittest.mock import MagicMock, patch

        ch = _make_channel()

        upload_resp = httpx.Response(
            200,
            json={"media_id": "media123"},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        send_resp = httpx.Response(
            200,
            json={"errcode": 0},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return upload_resp
            return send_resp

        ch._http = AsyncMock()
        ch._http.post = AsyncMock(side_effect=mock_post)

        attachment = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg")
        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="", user_id="u1", media=(attachment,))

        with patch("app.channels.media.downloader.MediaDownloader.download", new_callable=AsyncMock) as mock_download:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.data = b"image-bytes"
            mock_download.return_value = mock_result
            await ch.send(msg)

        assert ch._http.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_media_unsupported_type(self) -> None:
        ch = _make_channel()
        ch._http = AsyncMock()

        attachment = MediaAttachment(media_type=MediaType.DOCUMENT, url="https://example.com/doc.pdf")
        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="", user_id="u1", media=(attachment,))
        await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_media_no_url(self) -> None:
        ch = _make_channel()
        ch._http = AsyncMock()

        attachment = MediaAttachment(media_type=MediaType.IMAGE)
        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="", user_id="u1", media=(attachment,))
        await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_media_download_failure(self) -> None:
        ch = _make_channel()
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(side_effect=httpx.ConnectError("fail"))

        attachment = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg")
        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="", user_id="u1", media=(attachment,))
        await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_media_upload_no_media_id(self) -> None:
        ch = _make_channel()

        dl_resp = httpx.Response(
            200,
            content=b"image-bytes",
            request=httpx.Request("GET", "https://img.example.com/1.jpg"),
        )
        upload_resp = httpx.Response(
            200,
            json={"errcode": 40004},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )

        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=dl_resp)
        ch._http.post = AsyncMock(return_value=upload_resp)

        attachment = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg")
        msg = OutboundMessage(channel="wechat_official", recipient_id="user1", content="", user_id="u1", media=(attachment,))
        await ch.send(msg)


# ── Passive Reply ──────────────────────────────────────────────────────


class TestPassiveReply:
    def test_build_passive_reply(self) -> None:
        ch = _make_channel()
        xml = ch.build_passive_reply("user1", "bot1", "hello")
        assert "<ToUserName><![CDATA[user1]]></ToUserName>" in xml
        assert "<FromUserName><![CDATA[bot1]]></FromUserName>" in xml
        assert "<Content><![CDATA[hello]]></Content>" in xml
        assert "<MsgType><![CDATA[text]]></MsgType>" in xml


# ── Token Management ───────────────────────────────────────────────────


class TestTokenManagement:
    @pytest.mark.asyncio
    async def test_refresh_token_success(self) -> None:
        ch = _make_channel()
        mock_resp = httpx.Response(
            200,
            json={"access_token": "new_token", "expires_in": 7200},
            request=httpx.Request("GET", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)
        await ch._refresh_token()
        assert ch._access_token == "new_token"

    @pytest.mark.asyncio
    async def test_refresh_token_http_error(self) -> None:
        ch = _make_channel()
        mock_resp = httpx.Response(
            500,
            request=httpx.Request("GET", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)
        with pytest.raises(ChannelAuthError):
            await ch._refresh_token()

    @pytest.mark.asyncio
    async def test_refresh_token_api_error(self) -> None:
        ch = _make_channel()
        mock_resp = httpx.Response(
            200,
            json={"errcode": 40001, "errmsg": "invalid appid"},
            request=httpx.Request("GET", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)
        with pytest.raises(ChannelAuthError):
            await ch._refresh_token()

    @pytest.mark.asyncio
    async def test_ensure_token_refreshes_when_expired(self) -> None:
        ch = _make_channel()
        ch._token_expires_at = 0.0
        mock_resp = httpx.Response(
            200,
            json={"access_token": "refreshed", "expires_in": 7200},
            request=httpx.Request("GET", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)
        await ch._ensure_token()
        assert ch._access_token == "refreshed"

    @pytest.mark.asyncio
    async def test_ensure_token_skips_when_valid(self) -> None:
        ch = _make_channel()
        ch._http = AsyncMock()
        ch._http.get = AsyncMock()
        await ch._ensure_token()
        ch._http.get.assert_not_called()


# ── Rate Limit Error Mapping (直接测试 _call_customer_api) ────────────


class TestRateLimitErrorMapping:
    @pytest.mark.asyncio
    async def test_errcode_45015_raises_rate_limit_error(self) -> None:
        from app.channels.core.exceptions import RateLimitError

        ch = _make_channel()
        mock_resp = httpx.Response(
            200,
            json={"errcode": 45015, "errmsg": "out of response count limit"},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(RateLimitError, match="errcode=45015") as exc_info:
            await ch._call_customer_api({"touser": "u1", "msgtype": "text", "text": {"content": "hi"}})
        assert exc_info.value.retry_after == 5.0
        assert exc_info.value.channel == "wechat_official"

    @pytest.mark.asyncio
    async def test_errcode_45011_raises_rate_limit_error(self) -> None:
        from app.channels.core.exceptions import RateLimitError

        ch = _make_channel()
        mock_resp = httpx.Response(
            200,
            json={"errcode": 45011, "errmsg": "api freq out of limit"},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(RateLimitError, match="errcode=45011"):
            await ch._call_customer_api({"touser": "u1", "msgtype": "text", "text": {"content": "hi"}})

    @pytest.mark.asyncio
    async def test_errcode_45047_raises_rate_limit_error(self) -> None:
        from app.channels.core.exceptions import RateLimitError

        ch = _make_channel()
        mock_resp = httpx.Response(
            200,
            json={"errcode": 45047, "errmsg": "mass send limit"},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(RateLimitError, match="errcode=45047"):
            await ch._call_customer_api({"touser": "u1", "msgtype": "text", "text": {"content": "hi"}})

    @pytest.mark.asyncio
    async def test_non_rate_limit_errcode_raises_connection_error(self) -> None:
        from app.channels.core.exceptions import ChannelConnectionError

        ch = _make_channel()
        mock_resp = httpx.Response(
            200,
            json={"errcode": 48001, "errmsg": "api unauthorized"},
            request=httpx.Request("POST", "https://api.weixin.qq.com"),
        )
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(ChannelConnectionError, match="errcode=48001"):
            await ch._call_customer_api({"touser": "u1", "msgtype": "text", "text": {"content": "hi"}})
