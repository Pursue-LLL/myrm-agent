"""WeComChannel tests — contract, lifecycle, inbound, outbound, token, diagnostics."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelAuthError, ChannelSendError
from app.channels.media.downloader import MediaDownloadResult
from app.channels.providers.wecom.channel import WeComChannel
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


class TestWeComChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return WeComChannel(corp_id="test_corp", corp_secret="test_secret", agent_id=1000001)


# ── Helpers ───────────────────────────────────────────────────


def _make_channel() -> WeComChannel:
    ch = WeComChannel(
        corp_id="test_corp",
        corp_secret="test_secret",
        agent_id=1000001,
        token="test_token",
        encoding_aes_key="a" * 43,
    )
    ch._access_token = "mock_token"
    ch._token_expires_at = 9999999999.0
    return ch


def _ok_json(body: dict[str, object] | None = None) -> httpx.Response:
    return httpx.Response(200, json=body or {"errcode": 0, "errmsg": "ok"})


def _err_json(status: int = 400) -> httpx.Response:
    return httpx.Response(status, json={"errcode": status, "errmsg": "error"})


def _text_xml(content: str = "hello", from_user: str = "user1", msg_id: str = "m1") -> str:
    return (
        f"<xml><MsgType>text</MsgType><Content>{content}</Content>"
        f"<FromUserName>{from_user}</FromUserName><MsgId>{msg_id}</MsgId></xml>"
    )


def _image_xml(pic_url: str = "https://img.example.com/1.jpg") -> str:
    return f"<xml><MsgType>image</MsgType><PicUrl>{pic_url}</PicUrl><FromUserName>user1</FromUserName><MsgId>m2</MsgId></xml>"


def _voice_xml(media_id: str = "voice_mid") -> str:
    return f"<xml><MsgType>voice</MsgType><MediaId>{media_id}</MediaId><FromUserName>user1</FromUserName><MsgId>m3</MsgId></xml>"


def _location_xml() -> str:
    return (
        "<xml><MsgType>location</MsgType>"
        "<Location_X>39.9</Location_X><Location_Y>116.4</Location_Y>"
        "<Label>Beijing</Label>"
        "<FromUserName>user1</FromUserName><MsgId>m4</MsgId></xml>"
    )


def _link_xml() -> str:
    return (
        "<xml><MsgType>link</MsgType>"
        "<Title>Example</Title><Url>https://example.com</Url>"
        "<FromUserName>user1</FromUserName><MsgId>m5</MsgId></xml>"
    )


def _group_text_xml(content: str = "hello", chat_id: str = "grp1") -> str:
    return (
        f"<xml><MsgType>text</MsgType><Content>{content}</Content>"
        f"<FromUserName>user1</FromUserName><MsgId>m6</MsgId>"
        f"<ChatId>{chat_id}</ChatId></xml>"
    )


# ── Lifecycle ─────────────────────────────────────────────────


class TestWeComLifecycle:
    @pytest.mark.asyncio
    async def test_start_no_credentials(self) -> None:
        ch = WeComChannel(corp_id="", corp_secret="", agent_id=0)
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="secret", agent_id=1)
        token_resp = _ok_json({"errcode": 0, "access_token": "tok", "expires_in": 7200})
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=token_resp):
            await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._access_token == "tok"
        await ch._http.aclose()

    @pytest.mark.asyncio
    async def test_start_token_failure(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="secret", agent_id=1)
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=_err_json(401)):
            await ch.start()
        assert ch._status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._http, "aclose", new_callable=AsyncMock):
            await ch.stop()
        assert ch._status == ChannelStatus.STOPPED


class TestWeComHealthCheck:
    @pytest.mark.asyncio
    async def test_health_ok(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
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
        ch._access_token = ""
        ch._token_expires_at = 0.0
        with patch.object(ch._http, "get", new_callable=AsyncMock, side_effect=Exception("net")):
            assert await ch.health_check() is False


# ── Diagnostics ───────────────────────────────────────────────


class TestWeComDiagnostics:
    def test_no_corp_id(self) -> None:
        ch = WeComChannel(corp_id="", corp_secret="secret", agent_id=1)
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.CONFIG and "Corp ID" in i.message for i in issues)

    def test_no_corp_secret(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="", agent_id=1)
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.CONFIG and "Corp secret" in i.message for i in issues)

    def test_no_crypto(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="secret", agent_id=1)
        issues = ch.collect_issues()
        assert any(i.severity == IssueSeverity.WARNING and "Encryption" in i.message for i in issues)

    def test_error_status_auth_issue(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="secret", agent_id=1, token="tok", encoding_aes_key="a" * 43)
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.AUTH for i in issues)

    def test_healthy(self) -> None:
        ch = _make_channel()
        issues = ch.collect_issues()
        config_errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
        assert len(config_errors) == 0


# ── Token Management ──────────────────────────────────────────


class TestWeComToken:
    @pytest.mark.asyncio
    async def test_refresh_token_success(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="secret", agent_id=1)
        resp = _ok_json({"errcode": 0, "access_token": "new_tok", "expires_in": 7200})
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=resp):
            await ch._refresh_token()
        assert ch._access_token == "new_tok"
        assert ch._token_expires_at > 0
        await ch._http.aclose()

    @pytest.mark.asyncio
    async def test_refresh_token_http_error(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="secret", agent_id=1)
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=_err_json(500)):
            with pytest.raises(ChannelAuthError):
                await ch._refresh_token()
        await ch._http.aclose()

    @pytest.mark.asyncio
    async def test_refresh_token_errcode_nonzero(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="secret", agent_id=1)
        resp = _ok_json({"errcode": 40013, "errmsg": "invalid corpid"})
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(ChannelAuthError, match="invalid corpid"):
                await ch._refresh_token()
        await ch._http.aclose()

    @pytest.mark.asyncio
    async def test_refresh_token_non_json(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="secret", agent_id=1)
        resp = httpx.Response(200, content=b"not json")
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(ChannelAuthError, match="not JSON"):
                await ch._refresh_token()
        await ch._http.aclose()

    @pytest.mark.asyncio
    async def test_ensure_token_skips_if_valid(self) -> None:
        ch = _make_channel()
        with patch.object(ch, "_refresh_token", new_callable=AsyncMock) as mock_refresh:
            await ch._ensure_token()
        mock_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_token_refreshes_if_expired(self) -> None:
        ch = _make_channel()
        ch._token_expires_at = 0.0
        with patch.object(ch, "_refresh_token", new_callable=AsyncMock) as mock_refresh:
            await ch._ensure_token()
        mock_refresh.assert_called_once()


# ── Inbound: XML parsing ─────────────────────────────────────


class TestWeComInbound:
    @pytest.mark.asyncio
    async def test_text_message(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_callback(_text_xml("hello world"))
        assert len(emitted) == 1
        assert emitted[0].content == "hello world"
        assert emitted[0].sender_id == "user1"

    @pytest.mark.asyncio
    async def test_image_message(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_callback(_image_xml())
        assert len(emitted) == 1
        assert len(emitted[0].media) == 1
        assert emitted[0].media[0].media_type == MediaType.IMAGE

    @pytest.mark.asyncio
    async def test_voice_message_with_download(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        voice_resp = httpx.Response(200, content=b"audio_data", headers={"content-type": "audio/amr"})
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=voice_resp):
            await ch.handle_callback(_voice_xml())
        assert len(emitted) == 1
        assert emitted[0].media[0].media_type == MediaType.AUDIO

    @pytest.mark.asyncio
    async def test_location_message(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_callback(_location_xml())
        assert len(emitted) == 1
        assert "Beijing" in emitted[0].content
        assert "39.9" in emitted[0].content

    @pytest.mark.asyncio
    async def test_appmsg_message(self) -> None:
        xml = """<xml>
            <MsgType><![CDATA[appmsg]]></MsgType>
            <FromUserName><![CDATA[user1]]></FromUserName>
            <Title><![CDATA[Test File.pdf]]></Title>
            <Description><![CDATA[A test document]]></Description>
            <Url><![CDATA[http://example.com/file]]></Url>
            <MediaId><![CDATA[media123]]></MediaId>
        </xml>"""

        channel = WeComChannel(
            corp_id="corp",
            corp_secret="sec",
            agent_id=1,
            token="tok",
            encoding_aes_key="aes",
        )

        from app.channels.types import MediaAttachment, MediaType

        with patch.object(channel, "_download_inbound_media", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = MediaAttachment(media_type=MediaType.DOCUMENT, url="http://example.com/file")
            msg = await channel._parse_xml_message(ET.fromstring(xml))  # noqa: S314

        assert msg is not None
        assert "[AppMsg] Test File.pdf" in msg.content
        assert "A test document" in msg.content
        assert "http://example.com/file" in msg.content
        assert len(msg.media) == 1
        assert msg.media[0].media_type == MediaType.DOCUMENT

    @pytest.mark.asyncio
    async def test_link_message(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_callback(_link_xml())
        assert len(emitted) == 1
        assert "Example" in emitted[0].content
        assert "https://example.com" in emitted[0].content

    @pytest.mark.asyncio
    async def test_event_message_ignored(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        xml = "<xml><MsgType>event</MsgType><FromUserName>user1</FromUserName></xml>"
        await ch.handle_callback(xml)
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_empty_content_no_media_filtered(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        xml = "<xml><MsgType>text</MsgType><Content>  </Content><FromUserName>user1</FromUserName></xml>"
        await ch.handle_callback(xml)
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_group_message_with_mention(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_callback(_group_text_xml(f"@{ch._agent_id} hello"))
        assert len(emitted) == 1
        assert emitted[0].is_group is True
        assert emitted[0].mentioned is True

    @pytest.mark.asyncio
    async def test_group_message_no_mention(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_callback(_group_text_xml("just chatting"))
        assert len(emitted) == 1
        assert emitted[0].mentioned is False

    @pytest.mark.asyncio
    async def test_invalid_xml(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_callback("not xml at all")
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_bytes_input(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_callback(_text_xml("byte msg").encode("utf-8"))
        assert len(emitted) == 1
        assert emitted[0].content == "byte msg"


# ── Inbound: media download ──────────────────────────────────


class TestWeComMediaDownload:
    @pytest.mark.asyncio
    async def test_download_empty_media_id(self) -> None:
        ch = _make_channel()
        result = await ch._download_inbound_media("", MediaType.AUDIO)
        assert result is not None
        assert result.media_type == MediaType.AUDIO

    @pytest.mark.asyncio
    async def test_download_http_error(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=_err_json(404)):
            result = await ch._download_inbound_media("mid1", MediaType.IMAGE)
        assert result is not None
        assert result.media_type == MediaType.IMAGE

    @pytest.mark.asyncio
    async def test_download_json_error_response(self) -> None:
        ch = _make_channel()
        resp = httpx.Response(200, json={"errcode": 40007}, headers={"content-type": "application/json"})
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=resp):
            result = await ch._download_inbound_media("mid1", MediaType.VIDEO)
        assert result is not None
        assert result.media_type == MediaType.VIDEO

    @pytest.mark.asyncio
    async def test_download_exception(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "get", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await ch._download_inbound_media("mid1", MediaType.AUDIO)
        assert result is not None


# ── Outbound: send ────────────────────────────────────────────


class TestWeComSend:
    @pytest.mark.asyncio
    async def test_send_chunk_retry_failure(self) -> None:
        from app.channels.core.exceptions import ChannelSendError

        ch = _make_channel()

        # Mock _api_send to raise an exception
        async def mock_api_send(*args, **kwargs):
            raise ChannelSendError("simulated error", channel="wecom")

        with patch.object(ch, "_api_send", side_effect=mock_api_send):
            msg = OutboundMessage(channel="wecom", recipient_id="user1", content="Hello", user_id="U")
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        ch = _make_channel()
        send_resp = _ok_json()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=send_resp):
            msg = OutboundMessage(channel="wecom", recipient_id="user1", content="Hello", user_id="U")
            result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_with_media(self) -> None:
        ch = _make_channel()
        upload_resp = _ok_json({"errcode": 0, "media_id": "media_abc"})
        send_resp = _ok_json()
        with patch.object(ch._http, "post", new_callable=AsyncMock, side_effect=[upload_resp, send_resp]):
            msg = OutboundMessage(
                channel="wecom",
                recipient_id="user1",
                content="",
                user_id="U",
                media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg"),),
            )
            with patch(
                "app.channels.media.downloader.MediaDownloader.download",
                new_callable=AsyncMock,
                return_value=MediaDownloadResult(
                    success=True,
                    data=b"imgdata",
                    content_type="image/jpeg",
                    error=None,
                    url="https://img.example.com/1.jpg",
                    size_bytes=7,
                ),
            ):
                await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_placeholder(self) -> None:
        ch = _make_channel()
        send_resp = _ok_json()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=send_resp):
            result = await ch.send_placeholder("user1", "Thinking...")
        assert result == "sent"

    @pytest.mark.asyncio
    async def test_send_placeholder_failure(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_err_json(400)):
            result = await ch.send_placeholder("user1", "Thinking...")
        assert result is None


# ── Outbound: API send ────────────────────────────────────────


class TestWeComApiSend:
    @pytest.mark.asyncio
    async def test_api_send_success(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_ok_json()):
            result = await ch._api_send("user1", "text", {"content": "hi"})
        assert result is True

    @pytest.mark.asyncio
    async def test_api_send_http_error(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_err_json(500)):
            with pytest.raises(ChannelSendError):
                await ch._api_send("user1", "text", {"content": "hi"})

    @pytest.mark.asyncio
    async def test_api_send_errcode_nonzero(self) -> None:
        ch = _make_channel()
        resp = _ok_json({"errcode": 40014, "errmsg": "invalid access_token"})
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(ChannelSendError):
                await ch._api_send("user1", "text", {"content": "hi"})

    @pytest.mark.asyncio
    async def test_api_send_non_json_response(self) -> None:
        ch = _make_channel()
        resp = httpx.Response(200, content=b"not json")
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(ChannelSendError):
                await ch._api_send("user1", "text", {"content": "hi"})

    @pytest.mark.asyncio
    async def test_api_send_exception(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, side_effect=Exception("net")):
            with pytest.raises(ChannelSendError):
                await ch._api_send("user1", "text", {"content": "hi"})


# ── Media upload ──────────────────────────────────────────────


class TestWeComMediaUpload:
    @pytest.mark.asyncio
    async def test_upload_success(self) -> None:
        ch = _make_channel()
        resp = _ok_json({"errcode": 0, "media_id": "mid_123"})
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=resp):
            result = await ch._upload_media("image", b"data", "img.png", "image/png")
        assert result == "mid_123"

    @pytest.mark.asyncio
    async def test_upload_no_media_id(self) -> None:
        ch = _make_channel()
        resp = _ok_json({"errcode": 40004, "errmsg": "invalid media type"})
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=resp):
            result = await ch._upload_media("image", b"data", "img.png", "image/png")
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_non_json(self) -> None:
        ch = _make_channel()
        resp = httpx.Response(200, content=b"not json")
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=resp):
            result = await ch._upload_media("image", b"data", "img.png", "image/png")
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_exception(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await ch._upload_media("image", b"data", "img.png", "image/png")
        assert result is None


# ── Send media flow ───────────────────────────────────────────


class TestWeComSendMedia:
    @pytest.mark.asyncio
    async def test_send_media_from_path(self) -> None:
        import tempfile

        ch = _make_channel()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            f.flush()
            att = MediaAttachment(media_type=MediaType.IMAGE, path=f.name)

        upload_resp = _ok_json({"errcode": 0, "media_id": "mid_path"})
        send_resp = _ok_json()
        with patch.object(ch._http, "post", new_callable=AsyncMock, side_effect=[upload_resp, send_resp]):
            await ch._send_media("user1", att)

    @pytest.mark.asyncio
    async def test_send_media_from_url(self) -> None:
        ch = _make_channel()
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg")

        upload_resp = _ok_json({"errcode": 0, "media_id": "mid_url"})
        send_resp = _ok_json()
        with (
            patch(
                "app.channels.media.downloader.MediaDownloader.download",
                new_callable=AsyncMock,
                return_value=MediaDownloadResult(
                    success=True,
                    data=b"imgdata",
                    content_type="image/jpeg",
                    error=None,
                    url="https://img.example.com/1.jpg",
                    size_bytes=7,
                ),
            ),
            patch.object(ch._http, "post", new_callable=AsyncMock, side_effect=[upload_resp, send_resp]),
        ):
            await ch._send_media("user1", att)

    @pytest.mark.asyncio
    async def test_send_media_no_data(self) -> None:
        ch = _make_channel()
        att = MediaAttachment(media_type=MediaType.IMAGE)
        await ch._send_media("user1", att)

    @pytest.mark.asyncio
    async def test_send_media_path_read_error(self) -> None:
        ch = _make_channel()
        att = MediaAttachment(media_type=MediaType.IMAGE, path="/nonexistent/file.png")
        await ch._send_media("user1", att)


# ── Static helpers ────────────────────────────────────────────


class TestWeComStaticHelpers:
    def test_media_type_to_wecom(self) -> None:
        assert WeComChannel._media_type_to_wecom(MediaType.IMAGE) == "image"
        assert WeComChannel._media_type_to_wecom(MediaType.AUDIO) == "voice"
        assert WeComChannel._media_type_to_wecom(MediaType.VIDEO) == "video"
        assert WeComChannel._media_type_to_wecom(MediaType.DOCUMENT) == "file"

    def test_media_extension(self) -> None:
        assert WeComChannel._media_extension(MediaType.IMAGE) == "png"
        assert WeComChannel._media_extension(MediaType.AUDIO) == "amr"
        assert WeComChannel._media_extension(MediaType.VIDEO) == "mp4"
        assert WeComChannel._media_extension(MediaType.DOCUMENT) == "bin"


# ── Verify URL ────────────────────────────────────────────────


class TestWeComVerifyUrl:
    def test_no_crypto_raises(self) -> None:
        ch = WeComChannel(corp_id="corp", corp_secret="secret", agent_id=1)
        with pytest.raises(ValueError, match="crypto not configured"):
            ch.verify_url("sig", "ts", "nonce", "echo")

    def test_invalid_signature_raises(self) -> None:
        ch = _make_channel()
        assert ch._crypto is not None
        with patch.object(ch._crypto, "verify_signature", return_value=False):
            with pytest.raises(ValueError, match="Signature verification"):
                ch.verify_url("bad_sig", "ts", "nonce", "echo")

    def test_valid_signature(self) -> None:
        ch = _make_channel()
        assert ch._crypto is not None
        with patch.object(ch._crypto, "verify_signature", return_value=True):
            with patch.object(ch._crypto, "decrypt", return_value="decrypted_echo"):
                result = ch.verify_url("sig", "ts", "nonce", "echo")
        assert result == "decrypted_echo"


# ── Encrypted callback ────────────────────────────────────────


class TestWeComEncryptedCallback:
    @pytest.mark.asyncio
    async def test_encrypted_callback_success(self) -> None:
        ch = _make_channel()
        assert ch._crypto is not None
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        encrypted_xml = "<xml><Encrypt>encrypted_data</Encrypt></xml>"
        decrypted_xml = _text_xml("decrypted hello")

        with patch.object(ch._crypto, "verify_signature", return_value=True):
            with patch.object(ch._crypto, "decrypt", return_value=decrypted_xml):
                await ch.handle_callback(encrypted_xml, msg_signature="sig", timestamp="ts", nonce="n")

        assert len(emitted) == 1
        assert emitted[0].content == "decrypted hello"

    @pytest.mark.asyncio
    async def test_encrypted_callback_bad_signature(self) -> None:
        ch = _make_channel()
        assert ch._crypto is not None
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        encrypted_xml = "<xml><Encrypt>encrypted_data</Encrypt></xml>"
        with patch.object(ch._crypto, "verify_signature", return_value=False):
            await ch.handle_callback(encrypted_xml, msg_signature="bad", timestamp="ts", nonce="n")

        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_encrypted_callback_decrypt_error(self) -> None:
        ch = _make_channel()
        assert ch._crypto is not None
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        encrypted_xml = "<xml><Encrypt>encrypted_data</Encrypt></xml>"
        with patch.object(ch._crypto, "verify_signature", return_value=True):
            with patch.object(ch._crypto, "decrypt", side_effect=Exception("decrypt fail")):
                await ch.handle_callback(encrypted_xml, msg_signature="sig", timestamp="ts", nonce="n")

        assert len(emitted) == 0
