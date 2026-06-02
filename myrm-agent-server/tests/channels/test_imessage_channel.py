"""IMessageChannel tests — contract, lifecycle, inbound, outbound, reactions, diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.media.downloader import MediaDownloadResult
from app.channels.providers.imessage import (
    IMessageChannel,
    _filename_from_url,
    _mime_to_media_type,
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


class TestIMessageChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return IMessageChannel(api_url="http://localhost:1234", password="test_pass")


# ── Helpers ───────────────────────────────────────────────────


def _make_channel() -> IMessageChannel:
    return IMessageChannel(api_url="http://localhost:1234", password="test_pass")


def _ok_json(body: dict[str, object] | None = None) -> httpx.Response:
    return httpx.Response(200, json=body or {})


def _err_resp(status: int = 400) -> httpx.Response:
    return httpx.Response(status, json={"error": "fail"})


def _msg_event(
    text: str = "hello",
    sender: str = "+1234567890",
    chat_guid: str = "iMessage;-;+1234567890",
    msg_guid: str = "msg-001",
    is_from_me: bool = False,
    attachments: list[dict[str, object]] | None = None,
    thread_originator: str = "",
) -> dict[str, object]:
    data: dict[str, object] = {
        "text": text,
        "guid": msg_guid,
        "isFromMe": is_from_me,
        "handle": {"address": sender},
        "chats": [{"guid": chat_guid}],
    }
    if attachments:
        data["attachments"] = attachments
    if thread_originator:
        data["threadOriginatorGuid"] = thread_originator
    return {"type": "new-message", "data": data}


# ── Lifecycle ─────────────────────────────────────────────────


class TestIMessageLifecycle:
    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = _make_channel()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=mock_resp):
            await ch.start()
        assert ch._status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_retry_success(self) -> None:
        ch = _make_channel()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Network error")
            return mock_resp

        with patch.object(ch._http, "get", side_effect=mock_get):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_start_retry_failure(self) -> None:
        from app.channels.core.exceptions import ChannelConnectionError

        ch = _make_channel()

        async def mock_get(*args, **kwargs):
            raise Exception("Network error")

        with patch.object(ch._http, "get", side_effect=mock_get):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(ChannelConnectionError):
                    await ch.start()
        assert ch._status == ChannelStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_start_no_url(self) -> None:
        ch = IMessageChannel(api_url="", password="pass")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._http, "aclose", new_callable=AsyncMock):
            await ch.stop()
        assert ch._status == ChannelStatus.STOPPED


class TestIMessageHealthCheck:
    @pytest.mark.asyncio
    async def test_health_ok(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=_ok_json()):
            assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_stopped(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_http_error(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._http, "get", new_callable=AsyncMock, return_value=_err_resp(500)):
            assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_exception(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._http, "get", new_callable=AsyncMock, side_effect=Exception("net")):
            assert await ch.health_check() is False


# ── Diagnostics ───────────────────────────────────────────────


class TestIMessageDiagnostics:
    def test_no_url(self) -> None:
        ch = IMessageChannel(api_url="", password="pass")
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.CONFIG and "URL" in i.message for i in issues)

    def test_no_password(self) -> None:
        ch = IMessageChannel(api_url="http://localhost:1234", password="")
        issues = ch.collect_issues()
        assert any(i.severity == IssueSeverity.WARNING and "password" in i.message for i in issues)

    def test_error_status(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.RUNTIME for i in issues)

    def test_health_error(self) -> None:
        ch = _make_channel()
        ch.health.record_failure("Connection refused")
        issues = ch.collect_issues()
        assert any("Connection refused" in i.message for i in issues)

    def test_healthy(self) -> None:
        ch = _make_channel()
        issues = ch.collect_issues()
        config_errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
        assert len(config_errors) == 0


# ── Inbound: webhook ──────────────────────────────────────────


class TestIMessageInbound:
    @pytest.mark.asyncio
    async def test_text_message(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook(_msg_event(text="hi there"))
        assert len(emitted) == 1
        assert emitted[0].content == "hi there"
        assert emitted[0].sender_id == "+1234567890"

    @pytest.mark.asyncio
    async def test_from_me_filtered(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook(_msg_event(is_from_me=True))
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_empty_text_no_media_filtered(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook(_msg_event(text="  "))
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_non_message_event_ignored(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook({"type": "chat-read-status-changed", "data": {}})
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_invalid_data_type(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook({"type": "new-message", "data": "not a dict"})
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_group_message(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook(_msg_event(chat_guid="iMessage;+;chat123456"))
        assert len(emitted) == 1
        assert emitted[0].is_group is True

    @pytest.mark.asyncio
    async def test_attachment_parsed(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook(
            _msg_event(
                text="",
                attachments=[
                    {
                        "guid": "att-001",
                        "mimeType": "image/jpeg",
                        "transferName": "photo.jpg",
                    }
                ],
            )
        )
        assert len(emitted) == 1
        assert len(emitted[0].media) == 1
        assert emitted[0].media[0].media_type == MediaType.IMAGE
        assert "att-001" in (emitted[0].media[0].url or "")

    @pytest.mark.asyncio
    async def test_reply_to_parsed(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        await ch.handle_webhook(_msg_event(thread_originator="orig-guid"))
        assert len(emitted) == 1
        assert emitted[0].reply_to_id == "orig-guid"


class TestIMessageWebhookAuth:
    def test_verify_password_match(self) -> None:
        ch = _make_channel()
        assert ch.verify_webhook_password({"password": "test_pass"}) is True

    def test_verify_password_mismatch(self) -> None:
        ch = _make_channel()
        assert ch.verify_webhook_password({"password": "wrong"}) is False

    def test_verify_no_password_configured(self) -> None:
        ch = IMessageChannel(api_url="http://localhost:1234", password="")
        assert ch.verify_webhook_password({"password": "anything"}) is True


# ── Outbound: send ────────────────────────────────────────────


class TestIMessageSend:
    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        ch = _make_channel()
        resp = _ok_json({"data": {"guid": "sent-001"}})
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=resp):
            msg = OutboundMessage(
                channel="imessage",
                recipient_id="iMessage;-;+1234567890",
                content="Hello!",
                user_id="U",
            )
            result = await ch.send(msg)
        assert result == "sent-001"

    @pytest.mark.asyncio
    async def test_send_empty_recipient(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="imessage", recipient_id="", content="Hello!", user_id="U")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_text_http_error(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_err_resp(500)):
            msg = OutboundMessage(
                channel="imessage",
                recipient_id="chat1",
                content="Hello!",
                user_id="U",
            )
            result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_text_exception(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, side_effect=Exception("net")):
            msg = OutboundMessage(
                channel="imessage",
                recipient_id="chat1",
                content="Hello!",
                user_id="U",
            )
            result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_with_attachment(self) -> None:
        from app.channels.media import MediaDownloadResult

        ch = _make_channel()
        resp = _ok_json({"data": {"guid": "att-sent-001"}})
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=resp), patch(
            "app.channels.media.MediaDownloader.download",
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
            msg = OutboundMessage(
                channel="imessage",
                recipient_id="chat1",
                content="",
                user_id="U",
                media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg"),),
            )
            result = await ch.send(msg)
        assert result == "att-sent-001"

    @pytest.mark.asyncio
    async def test_send_attachment_no_data(self) -> None:
        ch = _make_channel()
        with patch(
            "app.channels.media.downloader.MediaDownloader.download",
            new_callable=AsyncMock,
            return_value=MediaDownloadResult(
                success=False, data=None, content_type=None,
                error=None, url="https://img.example.com/1.jpg", size_bytes=0,
            ),
        ):
            msg = OutboundMessage(
                channel="imessage",
                recipient_id="chat1",
                content="",
                user_id="U",
                media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg"),),
            )
            result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_attachment_http_error(self) -> None:
        ch = _make_channel()
        with patch(
            "app.channels.media.downloader.MediaDownloader.download",
            new_callable=AsyncMock,
            return_value=MediaDownloadResult(
                success=True, data=b"imgdata", content_type="image/jpeg",
                error=None, url="https://img.example.com/1.jpg", size_bytes=7,
            ),
        ), patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_err_resp(500)):
            msg = OutboundMessage(
                channel="imessage",
                recipient_id="chat1",
                content="",
                user_id="U",
                media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/1.jpg"),),
            )
            result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_attachment_from_path(self) -> None:
        import tempfile

        ch = _make_channel()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image")
            f.flush()

        resp = _ok_json({"data": {"guid": "path-sent"}})
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=resp):
            msg = OutboundMessage(
                channel="imessage",
                recipient_id="chat1",
                content="",
                user_id="U",
                media=(MediaAttachment(media_type=MediaType.IMAGE, path=f.name),),
            )
            result = await ch.send(msg)
        assert result == "path-sent"


# ── Reactions ─────────────────────────────────────────────────


class TestIMessageTapbackInbound:
    """Tests for inbound tapback reaction detection (_parse_tapback)."""

    @pytest.mark.asyncio
    async def test_tapback_like(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        event: dict[str, object] = {
            "type": "new-message",
            "data": {
                "guid": "msg-tapback-001",
                "isFromMe": False,
                "handle": {"address": "+1234567890"},
                "chats": [{"guid": "iMessage;-;+1234567890"}],
                "text": "",
                "associatedMessageType": 2001,
                "associatedMessageGuid": "p:0/msg-target-001",
            },
        }
        await ch.handle_webhook(event)
        assert len(emitted) == 1
        assert emitted[0].content == "\U0001F44D"
        assert emitted[0].message_id == "msg-target-001"
        assert emitted[0].metadata.get("reaction") is True
        assert emitted[0].metadata.get("target_message_id") == "msg-target-001"

    @pytest.mark.asyncio
    async def test_tapback_heart(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        event: dict[str, object] = {
            "type": "new-message",
            "data": {
                "guid": "msg-tapback-002",
                "isFromMe": False,
                "handle": {"address": "+9876543210"},
                "chats": [{"guid": "iMessage;-;+9876543210"}],
                "text": "",
                "associatedMessageType": 2000,
                "associatedMessageGuid": "msg-target-002",
            },
        }
        await ch.handle_webhook(event)
        assert len(emitted) == 1
        assert emitted[0].content == "\u2764\uFE0F"

    @pytest.mark.asyncio
    async def test_tapback_removal_ignored(self) -> None:
        """Tapback removal (3000+) should not emit inbound."""
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        event: dict[str, object] = {
            "type": "new-message",
            "data": {
                "guid": "msg-tapback-003",
                "isFromMe": False,
                "handle": {"address": "+1234567890"},
                "chats": [{"guid": "iMessage;-;+1234567890"}],
                "text": "",
                "associatedMessageType": 3001,
                "associatedMessageGuid": "msg-target-003",
            },
        }
        await ch.handle_webhook(event)
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_tapback_no_associated_type(self) -> None:
        """Normal message without associatedMessageType should not be treated as tapback."""
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        event: dict[str, object] = {
            "type": "new-message",
            "data": {
                "guid": "msg-004",
                "isFromMe": False,
                "handle": {"address": "+1234567890"},
                "chats": [{"guid": "iMessage;-;+1234567890"}],
                "text": "hello",
            },
        }
        await ch.handle_webhook(event)
        assert len(emitted) == 1
        assert emitted[0].content == "hello"
        assert emitted[0].metadata.get("reaction") is None

    @pytest.mark.asyncio
    async def test_tapback_unknown_code_ignored(self) -> None:
        """Unknown tapback code (e.g. 2099) has no emoji mapping, should skip."""
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        event: dict[str, object] = {
            "type": "new-message",
            "data": {
                "guid": "msg-tapback-005",
                "isFromMe": False,
                "handle": {"address": "+1234567890"},
                "chats": [{"guid": "iMessage;-;+1234567890"}],
                "text": "",
                "associatedMessageType": 2099,
                "associatedMessageGuid": "msg-target-005",
            },
        }
        await ch.handle_webhook(event)
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_tapback_in_group(self) -> None:
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        event: dict[str, object] = {
            "type": "new-message",
            "data": {
                "guid": "msg-tapback-006",
                "isFromMe": False,
                "handle": {"address": "+1234567890"},
                "chats": [{"guid": "iMessage;+;chat123456"}],
                "text": "",
                "associatedMessageType": 2002,
                "associatedMessageGuid": "p:1/msg-target-006",
            },
        }
        await ch.handle_webhook(event)
        assert len(emitted) == 1
        assert emitted[0].is_group is True
        assert emitted[0].content == "\U0001F44E"
        assert emitted[0].metadata.get("target_message_id") == "msg-target-006"

    @pytest.mark.asyncio
    async def test_tapback_no_guid_ignored(self) -> None:
        """Missing associatedMessageGuid should not emit."""
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        event: dict[str, object] = {
            "type": "new-message",
            "data": {
                "guid": "msg-tapback-007",
                "isFromMe": False,
                "handle": {"address": "+1234567890"},
                "chats": [{"guid": "iMessage;-;+1234567890"}],
                "text": "",
                "associatedMessageType": 2001,
                "associatedMessageGuid": "",
            },
        }
        await ch.handle_webhook(event)
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_tapback_from_me_filtered(self) -> None:
        """Tapback sent by self (isFromMe=True) should be filtered before parsing."""
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        event: dict[str, object] = {
            "type": "new-message",
            "data": {
                "guid": "msg-tapback-008",
                "isFromMe": True,
                "handle": {"address": "+1234567890"},
                "chats": [{"guid": "iMessage;-;+1234567890"}],
                "text": "",
                "associatedMessageType": 2001,
                "associatedMessageGuid": "msg-target-008",
            },
        }
        await ch.handle_webhook(event)
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_tapback_guid_only_prefix_no_content(self) -> None:
        """associatedMessageGuid='p:0/' (prefix with no actual guid) should not emit."""
        ch = _make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]

        event: dict[str, object] = {
            "type": "new-message",
            "data": {
                "guid": "msg-tapback-009",
                "isFromMe": False,
                "handle": {"address": "+1234567890"},
                "chats": [{"guid": "iMessage;-;+1234567890"}],
                "text": "",
                "associatedMessageType": 2001,
                "associatedMessageGuid": "p:0/",
            },
        }
        await ch.handle_webhook(event)
        assert len(emitted) == 0


class TestIMessageReactions:
    @pytest.mark.asyncio
    async def test_react_known_emoji(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.react_to_message("chat1", "msg1", "\u2764\uFE0F")
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload["reaction"] == 2000

    @pytest.mark.asyncio
    async def test_react_unknown_emoji_defaults(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.react_to_message("chat1", "msg1", "\U0001F525")
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload["reaction"] == 2001

    @pytest.mark.asyncio
    async def test_react_remove(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.react_to_message("chat1", "msg1", "")
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload["reaction"] == 3001

    @pytest.mark.asyncio
    async def test_react_http_error(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_err_resp(500)):
            await ch.react_to_message("chat1", "msg1", "")

    @pytest.mark.asyncio
    async def test_react_exception(self) -> None:
        ch = _make_channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, side_effect=Exception("net")):
            await ch.react_to_message("chat1", "msg1", "")


# ── Module helpers ────────────────────────────────────────────


class TestIMessageHelpers:
    def test_mime_to_media_type_image(self) -> None:
        assert _mime_to_media_type("image/jpeg") == MediaType.IMAGE

    def test_mime_to_media_type_audio(self) -> None:
        assert _mime_to_media_type("audio/mp4") == MediaType.AUDIO

    def test_mime_to_media_type_video(self) -> None:
        assert _mime_to_media_type("video/mp4") == MediaType.VIDEO

    def test_mime_to_media_type_document(self) -> None:
        assert _mime_to_media_type("application/pdf") == MediaType.DOCUMENT

    def test_filename_from_url(self) -> None:
        assert _filename_from_url("https://example.com/path/photo.jpg") == "photo.jpg"

    def test_filename_from_url_no_path(self) -> None:
        assert _filename_from_url("https://example.com/") == "download.bin"
