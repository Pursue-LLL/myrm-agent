"""Tests for Zalo channel implementation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.zalo import ZaloChannel
from app.channels.types import (
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase


class TestZaloChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return ZaloChannel(access_token="test_token")


class TestZaloInit:
    def test_default(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        assert ch._token == "tok123"


class TestZaloCollectIssues:
    def test_no_issues(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        issues = ch.collect_issues()
        assert len(issues) == 0

    def test_missing_token(self) -> None:
        ch = ZaloChannel(access_token="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.CONFIG
        assert issues[0].severity == IssueSeverity.ERROR
        assert "access_token" in issues[0].message

    def test_error_status(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.RUNTIME


class TestZaloHealthCheck:
    @pytest.mark.asyncio
    async def test_health_ok(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)
        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_fail(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_exception(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(side_effect=Exception("timeout"))
        assert await ch.health_check() is False


class TestZaloStart:
    @pytest.mark.asyncio
    async def test_start_no_token(self) -> None:
        ch = ZaloChannel(access_token="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_with_token(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        with patch.object(ch, "_fetch_oa_id", new_callable=AsyncMock, return_value="oa_123"):
            await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._bot_id == "oa_123"

    @pytest.mark.asyncio
    async def test_start_oa_fetch_fails(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        with patch.object(ch, "_fetch_oa_id", new_callable=AsyncMock, return_value=None):
            await ch.start()
        assert ch._status == ChannelStatus.RUNNING


class TestZaloStop:
    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED


class TestZaloSend:
    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        msg = MagicMock(spec=OutboundMessage)
        msg.recipient_id = "user123"
        msg.content = "hello"
        msg.attachments = []

        with patch.object(ch, "_send_text", new_callable=AsyncMock, return_value="mid1"):
            result = await ch.send(msg)
        assert result == "mid1"

    @pytest.mark.asyncio
    async def test_send_with_media(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        att = MediaAttachment(url="https://example.com/img.jpg", media_type=MediaType.IMAGE)

        msg = MagicMock(spec=OutboundMessage)
        msg.recipient_id = "user123"
        msg.content = ""
        msg.media = (att,)

        with patch.object(ch, "_send_media", new_callable=AsyncMock, return_value="mid2") as mock_sm:
            result = await ch.send(msg)
        assert result == "mid2"
        mock_sm.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_content(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        msg = MagicMock(spec=OutboundMessage)
        msg.recipient_id = "user123"
        msg.content = ""
        msg.attachments = []
        result = await ch.send(msg)
        assert result is None


class TestZaloWebhook:
    @pytest.mark.asyncio
    async def test_text_event(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        ch._inbound_handler = AsyncMock()

        body: dict[str, object] = {
            "event_name": "user_send_text",
            "sender": {"id": "sender1"},
            "message": {"msg_id": "m1", "text": "hello"},
        }
        await ch.handle_webhook(body)
        ch._inbound_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_image_event(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        ch._inbound_handler = AsyncMock()

        body: dict[str, object] = {
            "event_name": "user_send_image",
            "sender": {"id": "sender1"},
            "message": {"msg_id": "m2", "url": "https://img.zalo.me/pic.jpg"},
        }
        await ch.handle_webhook(body)
        ch._inbound_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_file_event(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        ch._inbound_handler = AsyncMock()

        body: dict[str, object] = {
            "event_name": "user_send_file",
            "sender": {"id": "sender1"},
            "message": {"msg_id": "m3", "url": "https://file.zalo.me/doc.pdf"},
        }
        await ch.handle_webhook(body)
        ch._inbound_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_event(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        ch._inbound_handler = AsyncMock()

        body: dict[str, object] = {"event_name": "unknown_event"}
        await ch.handle_webhook(body)
        ch._inbound_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_gif_event(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        ch._inbound_handler = AsyncMock()

        body: dict[str, object] = {
            "event_name": "user_send_gif",
            "sender": {"id": "sender1"},
            "message": {
                "msg_id": "m4",
                "url": "https://img.zalo.me/anim.gif",
                "thumb": "https://img.zalo.me/thumb.jpg",
            },
        }
        await ch.handle_webhook(body)
        ch._inbound_handler.assert_called_once()
        msg = ch._inbound_handler.call_args[0][0]
        assert len(msg.media) == 1
        assert msg.media[0].url == "https://img.zalo.me/anim.gif"

    @pytest.mark.asyncio
    async def test_missing_sender(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._status = ChannelStatus.RUNNING
        ch._inbound_handler = AsyncMock()

        body: dict[str, object] = {
            "event_name": "user_send_text",
            "message": {"msg_id": "m1", "text": "hello"},
        }
        await ch.handle_webhook(body)
        ch._inbound_handler.assert_called_once()
        inbound_msg = ch._inbound_handler.call_args[0][0]
        assert inbound_msg.sender_id == ""


class TestZaloPostMessage:
    @pytest.mark.asyncio
    async def test_post_message_success(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": 0, "data": {"message_id": "mid99"}}
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        result = await ch._post_message({"recipient": {"user_id": "u1"}, "message": {"text": "hi"}})
        assert result == "mid99"

    @pytest.mark.asyncio
    async def test_post_message_error_status(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        result = await ch._post_message({"recipient": {"user_id": "u1"}})
        assert result is None

    @pytest.mark.asyncio
    async def test_post_message_exception(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(side_effect=Exception("network"))

        result = await ch._post_message({"recipient": {"user_id": "u1"}})
        assert result is None

    @pytest.mark.asyncio
    async def test_post_message_api_error(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": -1, "message": "invalid token"}
        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=mock_resp)

        result = await ch._post_message({"recipient": {"user_id": "u1"}})
        assert result is None


class TestZaloSendText:
    @pytest.mark.asyncio
    async def test_send_text_delegates(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        with patch.object(ch, "_post_message", new_callable=AsyncMock, return_value="mid1") as mock_pm:
            result = await ch._send_text("user1", "hello")
        assert result == "mid1"
        call_payload = mock_pm.call_args[0][0]
        assert call_payload["recipient"]["user_id"] == "user1"
        assert call_payload["message"]["text"] == "hello"


class TestZaloUploadMedia:
    @pytest.mark.asyncio
    async def test_upload_from_url_success(self) -> None:
        from unittest.mock import patch

        ch = ZaloChannel(access_token="tok123")
        att = MediaAttachment(url="https://example.com/img.jpg", media_type=MediaType.IMAGE)

        upload_resp = MagicMock()
        upload_resp.status_code = 200
        upload_resp.json.return_value = {"error": 0, "data": {"attachment_id": "att123"}}

        ch._http = AsyncMock()
        ch._http.post = AsyncMock(return_value=upload_resp)

        with patch(
            "app.channels.media.downloader.MediaDownloader.download", new_callable=AsyncMock
        ) as mock_download:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.data = b"imgdata"
            mock_download.return_value = mock_result
            result = await ch._upload_media(att)

        assert result == "att123"

    @pytest.mark.asyncio
    async def test_upload_no_url_no_path(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        att = MediaAttachment(media_type=MediaType.IMAGE)
        result = await ch._upload_media(att)
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_download_fails(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        att = MediaAttachment(url="https://example.com/img.jpg", media_type=MediaType.IMAGE)

        ch._http = AsyncMock()
        ch._http.get = AsyncMock(side_effect=Exception("timeout"))

        result = await ch._upload_media(att)
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_api_error(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        att = MediaAttachment(url="https://example.com/img.jpg", media_type=MediaType.IMAGE)

        dl_resp = MagicMock()
        dl_resp.content = b"imgdata"
        dl_resp.raise_for_status = MagicMock()

        upload_resp = MagicMock()
        upload_resp.status_code = 500

        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=dl_resp)
        ch._http.post = AsyncMock(return_value=upload_resp)

        result = await ch._upload_media(att)
        assert result is None


class TestZaloSendMedia:
    @pytest.mark.asyncio
    async def test_send_media_image(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        att = MediaAttachment(url="https://example.com/img.jpg", media_type=MediaType.IMAGE)

        with (
            patch.object(ch, "_upload_media", new_callable=AsyncMock, return_value="att123"),
            patch.object(ch, "_post_message", new_callable=AsyncMock, return_value="mid2") as mock_pm,
        ):
            result = await ch._send_media("user1", att)
        assert result == "mid2"
        payload = mock_pm.call_args[0][0]
        elem = payload["message"]["attachment"]["payload"]["elements"][0]
        assert elem["media_type"] == "image"
        assert elem["attachment_id"] == "att123"

    @pytest.mark.asyncio
    async def test_send_media_upload_fails(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        att = MediaAttachment(url="https://example.com/img.jpg", media_type=MediaType.IMAGE)

        with patch.object(ch, "_upload_media", new_callable=AsyncMock, return_value=None):
            result = await ch._send_media("user1", att)
        assert result is None


class TestZaloFetchOaId:
    @pytest.mark.asyncio
    async def test_fetch_oa_id_success(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": 0, "data": {"oa_id": "oa_abc"}}
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)

        result = await ch._fetch_oa_id()
        assert result == "oa_abc"

    @pytest.mark.asyncio
    async def test_fetch_oa_id_failure(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(side_effect=Exception("network"))

        result = await ch._fetch_oa_id()
        assert result == ""

    @pytest.mark.asyncio
    async def test_fetch_oa_id_non_200(self) -> None:
        ch = ZaloChannel(access_token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        ch._http = AsyncMock()
        ch._http.get = AsyncMock(return_value=mock_resp)

        result = await ch._fetch_oa_id()
        assert result == ""
