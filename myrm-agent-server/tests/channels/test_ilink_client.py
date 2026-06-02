"""Tests for _ilink/client module (iLink Bot protocol HTTP client)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
)
from app.channels.providers._ilink.client import (
    ILinkClient,
)
from app.channels.providers._ilink.types import (
    CDNMediaType,
    FileItem,
    ILinkCredentials,
    ImageItem,
    ItemType,
    MediaInfo,
    MessageItem,
    TextItem,
    TypingStatus,
    VideoItem,
    VoiceItem,
    serialize_item,
)


def _make_creds() -> ILinkCredentials:
    return ILinkCredentials(
        bot_token="test_token",
        ilink_bot_id="bot123",
        base_url="https://ilinkai.weixin.qq.com",
        ilink_user_id="user456",
    )


def _make_client(creds: ILinkCredentials | None = None) -> ILinkClient:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    c = ILinkClient(creds or _make_creds(), http_client=mock_http)
    return c


def _ok_response(data: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json=data,
        request=httpx.Request("POST", "https://ilinkai.weixin.qq.com"),
    )


# ── Client Init ────────────────────────────────────────────────────────


class TestClientInit:
    def test_with_credentials(self) -> None:
        creds = _make_creds()
        c = _make_client(creds)
        assert c._creds == creds
        assert c._base_url == creds.base_url

    def test_without_credentials(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        c = ILinkClient(None, http_client=mock_http)
        assert c._creds is None
        assert c._base_url == "https://ilinkai.weixin.qq.com"

    def test_headers_with_auth(self) -> None:
        c = _make_client()
        headers = c._build_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test_token"
        assert headers["AuthorizationType"] == "ilink_bot_token"

    def test_headers_without_auth(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        c = ILinkClient(None, http_client=mock_http)
        headers = c._build_headers()
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_close_owned_client(self) -> None:
        c = ILinkClient(_make_creds())
        c._http = AsyncMock()
        c._http.aclose = AsyncMock()
        c._owns_http = True
        await c.close()
        c._http.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_external_client(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        c = ILinkClient(_make_creds(), http_client=mock_http)
        await c.close()
        mock_http.aclose.assert_not_called()


# ── POST error handling ────────────────────────────────────────────────


class TestPostErrors:
    @pytest.mark.asyncio
    async def test_connect_error(self) -> None:
        c = _make_client()
        c._http.post = AsyncMock(side_effect=httpx.ConnectError("fail"))
        with pytest.raises(ChannelConnectionError, match="connection failed"):
            await c._post("test", {})

    @pytest.mark.asyncio
    async def test_timeout_error(self) -> None:
        c = _make_client()
        c._http.post = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
        with pytest.raises(ChannelConnectionError, match="timeout"):
            await c._post("test", {})

    @pytest.mark.asyncio
    async def test_non_200_status(self) -> None:
        c = _make_client()
        resp = httpx.Response(500, request=httpx.Request("POST", "https://test.com"))
        c._http.post = AsyncMock(return_value=resp)
        with pytest.raises(ChannelConnectionError, match="HTTP 500"):
            await c._post("test", {})

    @pytest.mark.asyncio
    async def test_session_expired(self) -> None:
        c = _make_client()
        resp = _ok_response({"errcode": -14, "errmsg": "session expired"})
        c._http.post = AsyncMock(return_value=resp)
        with pytest.raises(ChannelAuthError, match="session expired"):
            await c._post("test", {})


# ── QR Login ───────────────────────────────────────────────────────────


class TestQRLogin:
    @pytest.mark.asyncio
    async def test_fetch_qr_code(self) -> None:
        c = _make_client()
        resp = httpx.Response(
            200,
            json={"qrcode": "qr123", "qrcode_img_content": "data:image/png;base64,..."},
            request=httpx.Request("GET", "https://ilinkai.weixin.qq.com"),
        )
        c._http.get = AsyncMock(return_value=resp)
        qrcode, img = await c.fetch_qr_code()
        assert qrcode == "qr123"
        assert "data:image" in img

    @pytest.mark.asyncio
    async def test_fetch_qr_code_http_error(self) -> None:
        c = _make_client()
        c._http.get = AsyncMock(side_effect=httpx.ConnectError("fail"))
        with pytest.raises(ChannelConnectionError):
            await c.fetch_qr_code()

    @pytest.mark.asyncio
    async def test_poll_qr_confirmed(self) -> None:
        c = _make_client()
        resp = httpx.Response(
            200,
            json={
                "status": "confirmed",
                "bot_token": "tok",
                "ilink_bot_id": "bid",
                "baseurl": "https://base.url",
                "ilink_user_id": "uid",
            },
            request=httpx.Request("GET", "https://ilinkai.weixin.qq.com"),
        )
        c._http.get = AsyncMock(return_value=resp)
        creds = await c.poll_qr_status("qr123")
        assert creds is not None
        assert creds.bot_token == "tok"
        assert creds.ilink_bot_id == "bid"

    @pytest.mark.asyncio
    async def test_poll_qr_waiting(self) -> None:
        c = _make_client()
        resp = httpx.Response(
            200,
            json={"status": "waiting"},
            request=httpx.Request("GET", "https://ilinkai.weixin.qq.com"),
        )
        c._http.get = AsyncMock(return_value=resp)
        result = await c.poll_qr_status("qr123")
        assert result is None

    @pytest.mark.asyncio
    async def test_poll_qr_expired(self) -> None:
        c = _make_client()
        resp = httpx.Response(
            200,
            json={"status": "expired"},
            request=httpx.Request("GET", "https://ilinkai.weixin.qq.com"),
        )
        c._http.get = AsyncMock(return_value=resp)
        with pytest.raises(ChannelAuthError, match="expired"):
            await c.poll_qr_status("qr123")

    @pytest.mark.asyncio
    async def test_poll_qr_timeout(self) -> None:
        c = _make_client()
        c._http.get = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
        result = await c.poll_qr_status("qr123")
        assert result is None


# ── Get Updates ────────────────────────────────────────────────────────


class TestGetUpdates:
    @pytest.mark.asyncio
    async def test_no_credentials(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        c = ILinkClient(None, http_client=mock_http)
        with pytest.raises(ChannelAuthError):
            await c.get_updates()

    @pytest.mark.asyncio
    async def test_success_with_messages(self) -> None:
        c = _make_client()
        resp = _ok_response(
            {
                "ret": 0,
                "get_updates_buf": "buf2",
                "msgs": [
                    {
                        "from_user_id": "user1",
                        "to_user_id": "bot1",
                        "message_type": 1,
                        "message_state": 0,
                        "item_list": [
                            {"type": 1, "text_item": {"text": "hello"}},
                        ],
                        "context_token": "ctx1",
                        "message_id": 42,
                    },
                ],
            }
        )
        c._http.post = AsyncMock(return_value=resp)
        messages, buf = await c.get_updates("buf1")
        assert buf == "buf2"
        assert len(messages) == 1
        assert messages[0].from_user_id == "user1"
        assert messages[0].item_list[0].text_item.text == "hello"

    @pytest.mark.asyncio
    async def test_success_empty(self) -> None:
        c = _make_client()
        resp = _ok_response({"ret": 0, "get_updates_buf": "buf1", "msgs": []})
        c._http.post = AsyncMock(return_value=resp)
        messages, buf = await c.get_updates("buf1")
        assert messages == []
        assert buf == "buf1"

    @pytest.mark.asyncio
    async def test_connection_error_returns_empty(self) -> None:
        c = _make_client()
        c._http.post = AsyncMock(side_effect=httpx.ConnectError("fail"))
        messages, buf = await c.get_updates("buf1")
        assert messages == []
        assert buf == "buf1"

    @pytest.mark.asyncio
    async def test_api_error(self) -> None:
        c = _make_client()
        resp = _ok_response({"ret": -1, "errcode": 100, "errmsg": "error"})
        c._http.post = AsyncMock(return_value=resp)
        with pytest.raises(ChannelConnectionError, match="getUpdates failed"):
            await c.get_updates()

    @pytest.mark.asyncio
    async def test_parse_image_item(self) -> None:
        c = _make_client()
        resp = _ok_response(
            {
                "ret": 0,
                "get_updates_buf": "buf",
                "msgs": [
                    {
                        "from_user_id": "u1",
                        "to_user_id": "b1",
                        "message_type": 1,
                        "message_state": 0,
                        "item_list": [
                            {
                                "type": 2,
                                "image_item": {
                                    "url": "https://img.example.com/1.jpg",
                                    "media": {
                                        "encrypt_query_param": "param1",
                                        "aes_key": "key1",
                                        "encrypt_type": 1,
                                    },
                                    "mid_size": 1024,
                                },
                            }
                        ],
                    }
                ],
            }
        )
        c._http.post = AsyncMock(return_value=resp)
        messages, _ = await c.get_updates()
        item = messages[0].item_list[0]
        assert item.type == ItemType.IMAGE
        assert item.image_item.url == "https://img.example.com/1.jpg"
        assert item.image_item.media.aes_key == "key1"

    @pytest.mark.asyncio
    async def test_parse_voice_item(self) -> None:
        c = _make_client()
        resp = _ok_response(
            {
                "ret": 0,
                "get_updates_buf": "buf",
                "msgs": [
                    {
                        "from_user_id": "u1",
                        "to_user_id": "b1",
                        "message_type": 1,
                        "message_state": 0,
                        "item_list": [
                            {
                                "type": 3,
                                "voice_item": {
                                    "text": "recognized text",
                                    "media": {"encrypt_query_param": "p", "aes_key": "k"},
                                    "playtime": 5000,
                                },
                            }
                        ],
                    }
                ],
            }
        )
        c._http.post = AsyncMock(return_value=resp)
        messages, _ = await c.get_updates()
        item = messages[0].item_list[0]
        assert item.type == ItemType.VOICE
        assert item.voice_item.text == "recognized text"
        assert item.voice_item.playtime == 5000

    @pytest.mark.asyncio
    async def test_parse_file_item(self) -> None:
        c = _make_client()
        resp = _ok_response(
            {
                "ret": 0,
                "get_updates_buf": "buf",
                "msgs": [
                    {
                        "from_user_id": "u1",
                        "to_user_id": "b1",
                        "message_type": 1,
                        "message_state": 0,
                        "item_list": [
                            {
                                "type": 4,
                                "file_item": {
                                    "file_name": "doc.pdf",
                                    "media": {"encrypt_query_param": "p", "aes_key": "k"},
                                },
                            }
                        ],
                    }
                ],
            }
        )
        c._http.post = AsyncMock(return_value=resp)
        messages, _ = await c.get_updates()
        item = messages[0].item_list[0]
        assert item.type == ItemType.FILE
        assert item.file_item.file_name == "doc.pdf"

    @pytest.mark.asyncio
    async def test_parse_video_item(self) -> None:
        c = _make_client()
        resp = _ok_response(
            {
                "ret": 0,
                "get_updates_buf": "buf",
                "msgs": [
                    {
                        "from_user_id": "u1",
                        "to_user_id": "b1",
                        "message_type": 1,
                        "message_state": 0,
                        "item_list": [
                            {
                                "type": 5,
                                "video_item": {
                                    "media": {"encrypt_query_param": "p", "aes_key": "k"},
                                    "video_size": 2048,
                                    "play_length": 10,
                                },
                            }
                        ],
                    }
                ],
            }
        )
        c._http.post = AsyncMock(return_value=resp)
        messages, _ = await c.get_updates()
        item = messages[0].item_list[0]
        assert item.type == ItemType.VIDEO
        assert item.video_item.video_size == 2048

    @pytest.mark.asyncio
    async def test_skip_invalid_msg_data(self) -> None:
        c = _make_client()
        resp = _ok_response(
            {
                "ret": 0,
                "get_updates_buf": "buf",
                "msgs": ["not a dict", None, 42],
            }
        )
        c._http.post = AsyncMock(return_value=resp)
        messages, _ = await c.get_updates()
        assert messages == []


# ── Send Message ───────────────────────────────────────────────────────


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        c = _make_client()
        resp = _ok_response({"ret": 0})
        c._http.post = AsyncMock(return_value=resp)

        items = [MessageItem(type=ItemType.TEXT, text_item=TextItem(text="hello"))]
        await c.send_message("user1", items, context_token="ctx1")
        c._http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_credentials(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        c = ILinkClient(None, http_client=mock_http)
        with pytest.raises(ChannelAuthError):
            await c.send_message("user1", [])

    @pytest.mark.asyncio
    async def test_send_api_error(self) -> None:
        c = _make_client()
        resp = _ok_response({"ret": -1, "errmsg": "send failed"})
        c._http.post = AsyncMock(return_value=resp)

        items = [MessageItem(type=ItemType.TEXT, text_item=TextItem(text="hello"))]
        with pytest.raises(ChannelConnectionError, match="sendMessage failed"):
            await c.send_message("user1", items)


# ── Serialize Item ─────────────────────────────────────────────────────


class TestSerializeItem:
    def test_text_item(self) -> None:
        item = MessageItem(type=ItemType.TEXT, text_item=TextItem(text="hello"))
        result = serialize_item(item)
        assert result == {"type": 1, "text_item": {"text": "hello"}}

    def test_image_item_with_url(self) -> None:
        item = MessageItem(type=ItemType.IMAGE, image_item=ImageItem(url="https://img.com/1.jpg"))
        result = serialize_item(item)
        assert result["image_item"]["url"] == "https://img.com/1.jpg"

    def test_image_item_with_media(self) -> None:
        media = MediaInfo(encrypt_query_param="p", aes_key="k", encrypt_type=1)
        item = MessageItem(type=ItemType.IMAGE, image_item=ImageItem(media=media))
        result = serialize_item(item)
        assert result["image_item"]["media"]["aes_key"] == "k"

    def test_file_item(self) -> None:
        media = MediaInfo(encrypt_query_param="p", aes_key="k")
        item = MessageItem(type=ItemType.FILE, file_item=FileItem(media=media, file_name="doc.pdf"))
        result = serialize_item(item)
        assert result["file_item"]["file_name"] == "doc.pdf"

    def test_video_item(self) -> None:
        media = MediaInfo(encrypt_query_param="p", aes_key="k")
        item = MessageItem(type=ItemType.VIDEO, video_item=VideoItem(media=media))
        result = serialize_item(item)
        assert "media" in result["video_item"]

    def test_voice_item(self) -> None:
        media = MediaInfo(encrypt_query_param="p", aes_key="k")
        item = MessageItem(type=ItemType.VOICE, voice_item=VoiceItem(media=media))
        result = serialize_item(item)
        assert "media" in result["voice_item"]


# ── Config & Typing ────────────────────────────────────────────────────


class TestConfigAndTyping:
    @pytest.mark.asyncio
    async def test_get_config(self) -> None:
        c = _make_client()
        resp = _ok_response({"ret": 0, "typing_ticket": "ticket123"})
        c._http.post = AsyncMock(return_value=resp)
        config = await c.get_config("user1")
        assert config["typing_ticket"] == "ticket123"

    @pytest.mark.asyncio
    async def test_get_config_no_creds(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        c = ILinkClient(None, http_client=mock_http)
        with pytest.raises(ChannelAuthError):
            await c.get_config("user1")

    @pytest.mark.asyncio
    async def test_get_config_api_error(self) -> None:
        c = _make_client()
        resp = _ok_response({"ret": -1, "errmsg": "error"})
        c._http.post = AsyncMock(return_value=resp)
        with pytest.raises(ChannelConnectionError):
            await c.get_config("user1")

    @pytest.mark.asyncio
    async def test_send_typing(self) -> None:
        c = _make_client()
        resp = _ok_response({"ret": 0})
        c._http.post = AsyncMock(return_value=resp)
        await c.send_typing("user1", "ticket1", TypingStatus.TYPING)
        c._http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_typing_no_creds(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        c = ILinkClient(None, http_client=mock_http)
        with pytest.raises(ChannelAuthError):
            await c.send_typing("user1", "ticket1", TypingStatus.TYPING)


# ── Upload URL ─────────────────────────────────────────────────────────


class TestGetUploadUrl:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        c = _make_client()
        resp = _ok_response({"ret": 0, "upload_param": "https://cdn.example.com/upload?key=val"})
        c._http.post = AsyncMock(return_value=resp)
        url = await c.get_upload_url("user1", CDNMediaType.IMAGE, 1024, "md5hash", "aeskey")
        assert "cdn.example.com" in url

    @pytest.mark.asyncio
    async def test_no_creds(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        c = ILinkClient(None, http_client=mock_http)
        with pytest.raises(ChannelAuthError):
            await c.get_upload_url("user1", CDNMediaType.IMAGE, 1024, "md5", "key")

    @pytest.mark.asyncio
    async def test_api_error(self) -> None:
        c = _make_client()
        resp = _ok_response({"ret": -1, "errmsg": "error"})
        c._http.post = AsyncMock(return_value=resp)
        with pytest.raises(ChannelConnectionError):
            await c.get_upload_url("user1", CDNMediaType.IMAGE, 1024, "md5", "key")
