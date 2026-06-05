"""SignalChannel tests — contract compliance, inbound parsing, outbound, diagnostics."""

from __future__ import annotations

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.media.downloader import MediaDownloadResult
from app.channels.providers.signal import (
    SignalChannel,
    _render_mentions,
)
from app.channels.types import InboundMessage

from .channel_test_base import ChannelTestBase

# ---------------------------------------------------------------------------
# Contract compliance (ChannelTestBase)
# ---------------------------------------------------------------------------


class TestSignalChannelBase(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel() -> tuple[SignalChannel, list[InboundMessage]]:
    from app.channels.core.allow_policy import AllowPolicy, ChatPolicy

    ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
    ch.allow_policy = AllowPolicy(group_policy=ChatPolicy.ALLOW)
    received: list[InboundMessage] = []

    async def _handler(msg: InboundMessage) -> None:
        received.append(msg)

    ch.set_inbound_handler(_handler)
    return ch, received


def _wrap_envelope(**envelope_fields: object) -> dict[str, object]:
    return {"envelope": envelope_fields}


# ---------------------------------------------------------------------------
# Mention rendering
# ---------------------------------------------------------------------------


class TestMentionRendering:
    def test_no_mentions_passthrough(self) -> None:
        assert _render_mentions("hello world", None) == "hello world"
        assert _render_mentions("hello world", []) == "hello world"

    def test_single_mention(self) -> None:
        text = "Hello \ufffc, how are you?"
        mentions = [{"start": 6, "length": 1, "number": "+1111111111"}]
        assert _render_mentions(text, mentions) == "Hello @+1111111111, how are you?"

    def test_multiple_mentions(self) -> None:
        text = "\ufffc and \ufffc"
        mentions = [
            {"start": 0, "length": 1, "number": "+111"},
            {"start": 6, "length": 1, "uuid": "uuid-abc"},
        ]
        result = _render_mentions(text, mentions)
        assert "@+111" in result
        assert "@uuid-abc" in result

    def test_uuid_fallback(self) -> None:
        text = "Hi \ufffc"
        mentions = [{"start": 3, "length": 1, "uuid": "some-uuid-123"}]
        assert _render_mentions(text, mentions) == "Hi @some-uuid-123"


# ---------------------------------------------------------------------------
# Inbound parsing
# ---------------------------------------------------------------------------


class TestInboundParsing:
    @pytest.mark.asyncio
    async def test_dm_message(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={"timestamp": 100, "message": "hello"},
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        msg = received[0]
        assert msg.content == "hello"
        assert msg.sender_id == "+9999999999"
        assert msg.chat_id == "+9999999999"
        assert msg.is_group is False
        assert msg.message_id == "100"

    @pytest.mark.asyncio
    async def test_group_message(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={
                "timestamp": 200,
                "message": "group hello",
                "groupInfo": {"groupId": "grp-abc", "groupName": "Test Group"},
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        msg = received[0]
        assert msg.chat_id == "grp-abc"
        assert msg.is_group is True
        assert msg.metadata.get("group_name") == "Test Group"

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={"timestamp": 300, "message": "   "},
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_attachment_parsed(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={
                "timestamp": 400,
                "message": "photo",
                "attachments": [
                    {"contentType": "image/jpeg", "filename": "photo.jpg"},
                ],
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert len(received[0].media) == 1
        assert received[0].media[0].media_type.value == "image"

    @pytest.mark.asyncio
    async def test_mention_detected(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={
                "timestamp": 500,
                "message": "Hey \ufffc check this",
                "mentions": [
                    {"start": 4, "length": 1, "number": "+1234567890"},
                ],
                "groupInfo": {"groupId": "grp-1"},
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert received[0].mentioned is True
        assert "@+1234567890" in received[0].content


# ---------------------------------------------------------------------------
# Self-message / syncMessage filtering
# ---------------------------------------------------------------------------


class TestSelfMessageFilter:
    @pytest.mark.asyncio
    async def test_own_phone_filtered(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+1234567890",
            dataMessage={"timestamp": 600, "message": "echo"},
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_sync_message_filtered(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            syncMessage=None,
            dataMessage={"timestamp": 700, "message": "sync transcript"},
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_own_uuid_filtered(self) -> None:
        from app.channels.core.allow_policy import AllowPolicy, ChatPolicy

        ch = SignalChannel(
            api_url="http://signal:8080",
            phone_number="+1234567890",
            account_uuid="my-uuid-abc",
        )
        ch.allow_policy = AllowPolicy(group_policy=ChatPolicy.ALLOW)
        received: list[InboundMessage] = []

        async def _handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(_handler)

        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            sourceUuid="my-uuid-abc",
            dataMessage={"timestamp": 850, "message": "from myself via uuid"},
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_other_sender_allowed(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+8888888888",
            dataMessage={"timestamp": 800, "message": "from other"},
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1


# ---------------------------------------------------------------------------
# Edit message
# ---------------------------------------------------------------------------


class TestEditMessage:
    @pytest.mark.asyncio
    async def test_edit_message_detected(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            editMessage={
                "targetSentTimestamp": 12345,
                "dataMessage": {
                    "timestamp": 900,
                    "message": "edited text",
                },
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert received[0].content == "edited text"
        assert received[0].metadata.get("edit_target_ts") == "12345"


# ---------------------------------------------------------------------------
# Reaction
# ---------------------------------------------------------------------------


class TestReactionHandling:
    @pytest.mark.asyncio
    async def test_reaction_emitted(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            reactionMessage={
                "emoji": "\U0001f44d",
                "targetAuthor": "+8888888888",
                "targetSentTimestamp": 1000,
                "isRemove": False,
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert received[0].content == "\U0001f44d"
        assert received[0].metadata.get("reaction") is True

    @pytest.mark.asyncio
    async def test_reaction_remove_ignored(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            reactionMessage={
                "emoji": "\U0001f44d",
                "targetAuthor": "+8888888888",
                "targetSentTimestamp": 1000,
                "isRemove": True,
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 0


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Attachment URL construction
# ---------------------------------------------------------------------------


class TestAttachmentUrl:
    @pytest.mark.asyncio
    async def test_attachment_url_constructed(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={
                "timestamp": 1100,
                "message": "with file",
                "attachments": [
                    {"contentType": "image/png", "filename": "pic.png", "id": "abc123"},
                ],
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert len(received[0].media) == 1
        assert received[0].media[0].url == "http://signal:8080/v1/attachments/abc123"

    @pytest.mark.asyncio
    async def test_attachment_no_id_no_url(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={
                "timestamp": 1200,
                "message": "no id",
                "attachments": [
                    {"contentType": "audio/ogg", "filename": "voice.ogg"},
                ],
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert received[0].media[0].url is None


# ---------------------------------------------------------------------------
# Group discovery
# ---------------------------------------------------------------------------


class TestListGroups:
    @pytest.mark.asyncio
    async def test_list_groups_returns_groups(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "grp1", "name": "Alpha"},
            {"id": "grp2", "name": "Beta"},
        ]
        ch._api._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        groups = await ch.list_groups()
        assert len(groups) == 2
        assert groups[0].jid == "grp1"
        assert groups[0].name == "Alpha"
        assert groups[1].jid == "grp2"

    @pytest.mark.asyncio
    async def test_list_groups_error_returns_empty(self) -> None:
        from unittest.mock import AsyncMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._api._http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))  # type: ignore[assignment]

        groups = await ch.list_groups()
        assert groups == []


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class TestSignalDiagnostics:
    def test_collect_issues_unconfigured(self) -> None:
        ch = SignalChannel(api_url="", phone_number="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind.value == "config"
        assert "Signal" in issues[0].message

    def test_collect_issues_healthy(self) -> None:
        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        assert ch.collect_issues() == []

    def test_collect_issues_runtime_error(self) -> None:
        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch.health.record_failure("Connection refused")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind.value == "runtime"
        assert "Connection refused" in issues[0].message

    def test_collect_issues_error_status(self) -> None:
        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert any(i.kind.value == "runtime" and "ERROR" in i.message for i in issues)

    def test_collect_issues_error_status_and_health(self) -> None:
        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.ERROR
        ch.health.record_failure("timeout")
        issues = ch.collect_issues()
        assert len(issues) == 2


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------


class TestSignalOutbound:
    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.types import OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"timestamp": 12345}
        ch._api._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content="Hello!")
        result = await ch.send(msg)
        assert result == "12345"

    @pytest.mark.asyncio
    async def test_send_empty_recipient(self) -> None:
        from app.channels.types import OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="", content="Hi")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_with_media(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.channels.types import MediaAttachment, MediaType, OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"timestamp": 67890}
        ch._api._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        with patch(
            "app.channels.media.downloader.MediaDownloader.download",
            new_callable=AsyncMock,
            return_value=MediaDownloadResult(
                success=True,
                data=b"\x89PNG",
                content_type="image/png",
                error=None,
                url="https://example.com/img.png",
                size_bytes=4,
            ),
        ):
            media = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png", mime_type="image/png")
            msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content="Photo", media=(media,))
            result = await ch.send(msg)
            assert result is not None

    @pytest.mark.asyncio
    async def test_send_failure_handled(self) -> None:
        from unittest.mock import AsyncMock

        from app.channels.types import OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._api._http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))  # type: ignore[assignment]

        msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content="Hi")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        ch._api._http.put = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        await ch.start_typing("+9999")
        ch._api._http.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_typing(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        ch._api._http.delete = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        await ch.stop_typing("+9999")
        ch._api._http.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        ch._api._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        await ch.react_to_message("+9999", "12345", "\U0001f44d")
        ch._api._http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_to_message_non_digit_id(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        ch._api._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        await ch.react_to_message("+9999", "not-a-number", "\U0001f44d")
        ch._api._http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_to_message_error(self) -> None:
        from unittest.mock import AsyncMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._api._http.post = AsyncMock(side_effect=Exception("network"))  # type: ignore[assignment]

        await ch.react_to_message("+9999", "12345", "\U0001f44d")

    @pytest.mark.asyncio
    async def test_send_text_non_201(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.types import OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        ch._api._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content="Hello!")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_no_content_no_media(self) -> None:
        from app.channels.types import OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content="")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_with_media_from_path(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.channels.types import MediaAttachment, MediaType, OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"timestamp": 11111}
        ch._api._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=b"\x89PNG"):
            media = MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/img.png", mime_type="image/png")
            msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content="", media=(media,))
            result = await ch.send(msg)
            assert result is not None

    @pytest.mark.asyncio
    async def test_send_with_media_path_error(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.channels.types import MediaAttachment, MediaType, OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"timestamp": 22222}
        ch._api._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        with patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=FileNotFoundError("not found")):
            media = MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/missing.png", mime_type="image/png")
            msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content="text", media=(media,))
            result = await ch.send(msg)
            assert result is not None

    @pytest.mark.asyncio
    async def test_send_with_media_no_data(self) -> None:
        from app.channels.types import MediaAttachment, MediaType, OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        media = MediaAttachment(media_type=MediaType.IMAGE)
        msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content="", media=(media,))
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_with_media_download_returns_none(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.channels.types import MediaAttachment, MediaType, OutboundMessage

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"timestamp": 33333}
        ch._api._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        with patch(
            "app.channels.media.downloader.MediaDownloader.download",
            new_callable=AsyncMock,
            return_value=MediaDownloadResult(
                success=False,
                data=None,
                content_type=None,
                error=None,
                url="https://example.com/bad.png",
                size_bytes=0,
            ),
        ):
            media = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/bad.png")
            msg = OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content="text", media=(media,))
            result = await ch.send(msg)
            assert result is not None

    @pytest.mark.asyncio
    async def test_typing_start_error_silenced(self) -> None:
        from unittest.mock import AsyncMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._api._http.put = AsyncMock(side_effect=Exception("fail"))  # type: ignore[assignment]
        await ch.start_typing("+9999")

    @pytest.mark.asyncio
    async def test_typing_stop_error_silenced(self) -> None:
        from unittest.mock import AsyncMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._api._http.delete = AsyncMock(side_effect=Exception("fail"))  # type: ignore[assignment]
        await ch.stop_typing("+9999")


# ---------------------------------------------------------------------------
# SignalClient API tests
# ---------------------------------------------------------------------------


class TestSignalClientApi:
    @pytest.mark.asyncio
    async def test_health_check_ok(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        ok, err = await client.health_check()
        assert ok is True
        assert err == ""

    @pytest.mark.asyncio
    async def test_health_check_fail(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        ok, err = await client.health_check()
        assert ok is False
        assert "503" in err

    @pytest.mark.asyncio
    async def test_list_groups_ok(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"id": "g1"}, {"id": "g2"}]
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        groups = await client.list_groups()
        assert len(groups) == 2

    @pytest.mark.asyncio
    async def test_list_groups_non_200(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        groups = await client.list_groups()
        assert groups == []

    @pytest.mark.asyncio
    async def test_list_groups_non_list_response(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "not found"}
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        groups = await client.list_groups()
        assert groups == []

    @pytest.mark.asyncio
    async def test_send_message(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        client._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        resp = await client.send_message({"message": "hi", "number": "+1234567890", "recipients": ["+9999"]})
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        client._http.put = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        await client.start_typing("+9999")
        client._http.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_typing(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        client._http.delete = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        await client.stop_typing()
        client._http.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_reaction(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        client._http.post = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        await client.send_reaction("+9999", "\U0001f44d", "+8888", 12345)
        client._http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_ok(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"envelope": {}}]
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        msgs = await client.receive()
        assert len(msgs) == 1

    @pytest.mark.asyncio
    async def test_receive_non_200(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        msgs = await client.receive()
        assert msgs == []

    @pytest.mark.asyncio
    async def test_receive_non_list(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = "not a list"
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        msgs = await client.receive()
        assert msgs == []

    @pytest.mark.asyncio
    async def test_download_attachment_ok(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG"
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        data = await client.download_attachment("att-123")
        assert data == b"\x89PNG"

    @pytest.mark.asyncio
    async def test_download_attachment_not_found(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        data = await client.download_attachment("att-missing")
        assert data is None

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        from unittest.mock import AsyncMock

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        client._http.aclose = AsyncMock()  # type: ignore[method-assign]
        await client.close()
        client._http.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# Inbound edge cases
# ---------------------------------------------------------------------------


class TestInboundEdgeCases:
    @pytest.mark.asyncio
    async def test_no_envelope(self) -> None:
        ch, received = _make_channel()
        await ch._handle_envelope({})  # type: ignore[arg-type]
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_envelope_not_dict(self) -> None:
        ch, received = _make_channel()
        await ch._handle_envelope({"envelope": "not-a-dict"})  # type: ignore[arg-type]
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_no_source(self) -> None:
        ch, received = _make_channel()
        await ch._handle_envelope({"envelope": {"dataMessage": {"message": "hi"}}})  # type: ignore[arg-type]
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_source_from_source_field(self) -> None:
        ch, received = _make_channel()
        payload = {"envelope": {"source": "+7777777777", "dataMessage": {"timestamp": 1, "message": "hi"}}}
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert received[0].sender_id == "+7777777777"

    @pytest.mark.asyncio
    async def test_attachment_non_dict_skipped(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={"timestamp": 1, "message": "hi", "attachments": ["not-a-dict"]},
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert len(received[0].media) == 0

    @pytest.mark.asyncio
    async def test_mention_uuid_check(self) -> None:
        from app.channels.core.allow_policy import AllowPolicy, ChatPolicy

        ch = SignalChannel(
            api_url="http://signal:8080",
            phone_number="+1234567890",
            account_uuid="my-uuid",
        )
        ch.allow_policy = AllowPolicy(group_policy=ChatPolicy.ALLOW)
        received: list[InboundMessage] = []

        async def _handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(_handler)

        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={
                "timestamp": 1,
                "message": "Hey \ufffc",
                "mentions": [{"start": 4, "length": 1, "uuid": "my-uuid"}],
                "groupInfo": {"groupId": "g1"},
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert received[0].mentioned is True

    @pytest.mark.asyncio
    async def test_check_mentioned_non_list(self) -> None:
        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        assert ch._check_mentioned("not-a-list") is False
        assert ch._check_mentioned(None) is False

    @pytest.mark.asyncio
    async def test_list_groups_non_dict_entry(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [42, {"id": "g1", "name": "G"}, "bad"]
        ch._api._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        groups = await ch.list_groups()
        assert len(groups) == 1
        assert groups[0].jid == "g1"

    @pytest.mark.asyncio
    async def test_list_groups_internal_id_fallback(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"internal_id": "int-1", "name": "Fallback"}]
        ch._api._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        groups = await ch.list_groups()
        assert len(groups) == 1
        assert groups[0].jid == "int-1"

    @pytest.mark.asyncio
    async def test_health_check_api_returns_false(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.RUNNING
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        ch._api._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        result = await ch.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_degraded_state(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.DEGRADED
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        ch._api._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        result = await ch.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_reaction_empty_emoji_ignored(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            reactionMessage={
                "emoji": "",
                "targetAuthor": "+8888888888",
                "targetSentTimestamp": 1000,
                "isRemove": False,
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 0


# ---------------------------------------------------------------------------
# Start with poll task
# ---------------------------------------------------------------------------


class TestSignalStart:
    @pytest.mark.asyncio
    async def test_start_creates_inbound_task(self) -> None:
        import asyncio

        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._inbound_task is not None
        ch._status = ChannelStatus.STOPPED
        ch._inbound_task.cancel()
        try:
            await ch._inbound_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_stop_cancels_inbound_task(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock

        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.RUNNING

        async def _fake_poll() -> None:
            await asyncio.sleep(100)

        ch._inbound_task = asyncio.create_task(_fake_poll())
        ch._api._http.aclose = AsyncMock()  # type: ignore[method-assign]

        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        assert ch._inbound_task.cancelled() or ch._inbound_task.done()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestSignalLifecycle:
    @pytest.mark.asyncio
    async def test_start_no_config(self) -> None:
        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="", phone_number="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.RUNNING
        ch._inbound_task = None
        ch._api._http = MagicMock()
        ch._api._http.aclose = AsyncMock()

        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_health_check_running(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.RUNNING
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        ch._api._http.get = AsyncMock(return_value=mock_resp)  # type: ignore[assignment]

        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_stopped(self) -> None:
        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        from unittest.mock import AsyncMock

        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.RUNNING
        ch._api._http.get = AsyncMock(side_effect=Exception("network"))  # type: ignore[assignment]

        assert await ch.health_check() is False


# ---------------------------------------------------------------------------
# Reply-to / quote
# ---------------------------------------------------------------------------


class TestReplyTo:
    @pytest.mark.asyncio
    async def test_quote_reply_to_id(self) -> None:
        ch, received = _make_channel()
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={
                "timestamp": 1300,
                "message": "replying",
                "quote": {"id": 999, "author": "+8888888888", "text": "original"},
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert received[0].reply_to_id == "999"

    @pytest.mark.asyncio
    async def test_data_message_reaction(self) -> None:
        ch, received = _make_channel()
        thumbs_up = "\U0001f44d"
        payload = _wrap_envelope(
            sourceNumber="+9999999999",
            dataMessage={
                "timestamp": 1400,
                "reaction": {
                    "emoji": thumbs_up,
                    "targetAuthor": "+8888888888",
                    "targetSentTimestamp": 1000,
                    "isRemove": False,
                },
            },
        )
        await ch._handle_envelope(payload)  # type: ignore[arg-type]
        assert len(received) == 1
        assert received[0].content == thumbs_up


# ---------------------------------------------------------------------------
# WebSocket / inbound mode selection
# ---------------------------------------------------------------------------


class _FakeWS:
    """Fake WebSocket that yields pre-defined messages as async iterator."""

    def __init__(self, messages: list[str | bytes]) -> None:
        self._messages = messages

    def __aiter__(self) -> _FakeWS:
        self._iter = iter(self._messages)
        return self

    async def __anext__(self) -> str | bytes:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class TestWebSocketInbound:
    @pytest.mark.asyncio
    async def test_ws_url_construction(self) -> None:
        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        assert client.ws_url == "ws://signal:8080/v1/receive/+1234567890"

    @pytest.mark.asyncio
    async def test_ws_url_https(self) -> None:
        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("https://signal.example.com", "+1234567890")
        assert client.ws_url == "wss://signal.example.com/v1/receive/+1234567890"

    @pytest.mark.asyncio
    async def test_ws_url_trailing_slash(self) -> None:
        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080/", "+1234567890")
        assert client.ws_url == "ws://signal:8080/v1/receive/+1234567890"

    @pytest.mark.asyncio
    async def test_stream_events_yields_parsed_json(self) -> None:
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        envelope = {"envelope": {"sourceNumber": "+9999", "dataMessage": {"message": "hi"}}}

        mock_connect = MagicMock()
        mock_connect.return_value.__aenter__ = AsyncMock(return_value=_FakeWS([json.dumps(envelope)]))
        mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("websockets.asyncio.client.connect", mock_connect):
            results = []
            async for event in client.stream_events():
                results.append(event)
            assert len(results) == 1
            assert results[0]["envelope"]["sourceNumber"] == "+9999"

    @pytest.mark.asyncio
    async def test_stream_events_handles_bytes(self) -> None:
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")
        envelope = {"envelope": {"sourceNumber": "+9999"}}

        mock_connect = MagicMock()
        mock_connect.return_value.__aenter__ = AsyncMock(return_value=_FakeWS([json.dumps(envelope).encode()]))
        mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("websockets.asyncio.client.connect", mock_connect):
            results = []
            async for event in client.stream_events():
                results.append(event)
            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_stream_events_skips_invalid_json(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.channels.providers.signal.api import SignalClient

        client = SignalClient("http://signal:8080", "+1234567890")

        mock_connect = MagicMock()
        mock_connect.return_value.__aenter__ = AsyncMock(return_value=_FakeWS(["not-json", '{"valid": true}']))
        mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("websockets.asyncio.client.connect", mock_connect):
            results = []
            async for event in client.stream_events():
                results.append(event)
            assert len(results) == 1
            assert results[0]["valid"] is True

    @pytest.mark.asyncio
    async def test_select_inbound_mode_ws_success(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")

        mock_connect = MagicMock()
        mock_connect.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("websockets.asyncio.client.connect", mock_connect):
            result = await ch._select_inbound_mode()

        assert ch._using_websocket is True
        assert result == ch._ws_connect

    @pytest.mark.asyncio
    async def test_select_inbound_mode_ws_failure(self) -> None:
        from unittest.mock import patch

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")

        with patch("websockets.asyncio.client.connect", side_effect=ConnectionRefusedError("refused")):
            result = await ch._select_inbound_mode()

        assert ch._using_websocket is False
        assert result == ch._poll_once

    @pytest.mark.asyncio
    async def test_ws_connect_processes_envelopes(self) -> None:
        from unittest.mock import patch

        ch, received = _make_channel()
        envelope = {
            "envelope": {
                "sourceNumber": "+9999999999",
                "dataMessage": {"timestamp": 2000, "message": "hello via ws"},
            }
        }

        async def _fake_stream() -> None:
            yield envelope  # type: ignore[misc]

        with patch.object(ch._api, "stream_events", _fake_stream):
            await ch._ws_connect()

        assert len(received) == 1
        assert received[0].content == "hello via ws"

    @pytest.mark.asyncio
    async def test_poll_once_processes_messages(self) -> None:
        from unittest.mock import AsyncMock

        from app.channels.core.base import ChannelStatus

        ch, received = _make_channel()
        ch._status = ChannelStatus.RUNNING
        envelope = {
            "envelope": {
                "sourceNumber": "+9999999999",
                "dataMessage": {"timestamp": 3000, "message": "hello via poll"},
            }
        }

        call_count = 0

        async def _fake_receive() -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [envelope]
            ch._status = ChannelStatus.STOPPED
            return []

        ch._api.receive = AsyncMock(side_effect=_fake_receive)  # type: ignore[method-assign]

        await ch._poll_once()

        assert len(received) == 1
        assert received[0].content == "hello via poll"

    @pytest.mark.asyncio
    async def test_collect_issues_polling_fallback_warning(self) -> None:
        from app.channels.core.base import ChannelStatus
        from app.channels.types import IssueSeverity

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.RUNNING
        ch._using_websocket = False

        issues = ch.collect_issues()
        warnings = [i for i in issues if i.severity == IssueSeverity.WARNING]
        assert len(warnings) == 1
        assert "HTTP polling" in warnings[0].message
        assert warnings[0].fix is not None
        assert "WebSocket" in (warnings[0].fix or "")

    @pytest.mark.asyncio
    async def test_collect_issues_ws_mode_no_warning(self) -> None:
        from app.channels.core.base import ChannelStatus
        from app.channels.types import IssueSeverity

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
        ch._status = ChannelStatus.RUNNING
        ch._using_websocket = True

        issues = ch.collect_issues()
        warnings = [i for i in issues if i.severity == IssueSeverity.WARNING]
        assert len(warnings) == 0

    @pytest.mark.asyncio
    async def test_start_with_ws_mode(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.channels.core.base import ChannelStatus

        ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")

        mock_connect = MagicMock()
        mock_connect.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("websockets.asyncio.client.connect", mock_connect):
            await ch.start()

        assert ch._status == ChannelStatus.RUNNING
        assert ch._using_websocket is True
        assert ch._inbound_task is not None

        ch._status = ChannelStatus.STOPPED
        ch._inbound_task.cancel()
        try:
            await ch._inbound_task
        except asyncio.CancelledError:
            pass
