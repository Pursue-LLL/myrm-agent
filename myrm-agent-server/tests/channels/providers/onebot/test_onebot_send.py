"""OneBot outbound: what the client does not take is raised or reported, never dropped."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.onebot.channel import OneBotChannel
from app.channels.providers.onebot.helpers import build_onebot_message, can_send_media
from app.channels.types import MediaAttachment, MediaType, OutboundMessage


def _channel(*responses: dict[str, object]) -> OneBotChannel:
    ch = OneBotChannel(host="127.0.0.1", port=3001)
    ch._active_ws = MagicMock()
    ch._active_ws.closed = False
    ch._call_api = AsyncMock(side_effect=list(responses) or [{"status": "ok", "data": {"message_id": 1}}])
    return ch


def _message(*media: MediaAttachment, content: str = "", recipient_id: str = "123456789") -> OutboundMessage:
    return OutboundMessage(channel="onebot", recipient_id=recipient_id, content=content, user_id="u1", media=media)


def _image(url: str = "https://img.example.com/a.png") -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.IMAGE, url=url)


def _document() -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.DOCUMENT, path="/tmp/report.pdf")


class TestRequestFailures:
    @pytest.mark.asyncio
    async def test_no_connected_client_is_a_retriable_failure(self) -> None:
        ch = OneBotChannel(host="127.0.0.1", port=3001)
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(content="hi"))
        assert exc_info.value.retriable is True

    @pytest.mark.asyncio
    async def test_non_numeric_recipient_is_permanent(self) -> None:
        ch = _channel()
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(content="hi", recipient_id="alice"))
        assert exc_info.value.retriable is False
        ch._call_api.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("retcode", "retriable"), [(1400, False), (1403, False), (1404, False), (100, True), (1200, True)])
    async def test_failed_status_is_classified_by_retcode(self, retcode: int, retriable: bool) -> None:
        ch = _channel({"status": "failed", "retcode": retcode, "wording": "muted"})
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(content="hi"))

        assert exc_info.value.retriable is retriable
        assert "muted" in str(exc_info.value)
        assert "muted" in (ch.health.last_error or "")

    @pytest.mark.asyncio
    async def test_api_timeout_is_a_retriable_failure(self) -> None:
        ch = _channel()
        ch._call_api = AsyncMock(side_effect=TimeoutError())
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(content="hi"))
        assert exc_info.value.retriable is True

    @pytest.mark.asyncio
    async def test_a_failing_later_chunk_is_raised_not_swallowed(self) -> None:
        ch = _channel({"status": "ok", "data": {"message_id": 1}}, {"status": "failed", "retcode": 100})
        with (
            patch("app.channels.providers.onebot.channel.render", return_value=["one", "two"]),
            patch("app.channels.providers.onebot.channel.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ChannelSendError) as exc_info,
        ):
            await ch.send(_message(content="long"))
        assert exc_info.value.retriable is True


class TestAttachments:
    @pytest.mark.asyncio
    async def test_files_only_image_is_one_message_without_text(self) -> None:
        ch = _channel({"status": "ok", "data": {"message_id": 7}})
        result = await ch.send(_message(_image()))

        assert result == "7"
        (call,) = ch._call_api.await_args_list
        assert call.args[1]["message"] == [{"type": "image", "data": {"file": "https://img.example.com/a.png"}}]

    @pytest.mark.asyncio
    async def test_unsupported_attachment_is_reported_after_the_text_went_out(self) -> None:
        ch = _channel()
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(_document(), _image(), content="Here you go"))

        (call,) = ch._call_api.await_args_list
        assert [seg["type"] for seg in call.args[1]["message"]] == ["image", "text"]
        assert exc_info.value.accepted is True
        assert exc_info.value.retriable is False
        assert exc_info.value.failed_attachments == ("report.pdf",)

    @pytest.mark.asyncio
    async def test_only_unsupported_attachments_send_nothing(self) -> None:
        ch = _channel()
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(_document()))

        ch._call_api.assert_not_awaited()
        assert exc_info.value.accepted is False
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_empty_message_is_a_no_op(self) -> None:
        ch = _channel()
        assert await ch.send(_message()) is None
        ch._call_api.assert_not_awaited()


class TestSegments:
    def test_local_file_becomes_a_file_uri(self) -> None:
        local = MediaAttachment(media_type=MediaType.AUDIO, path="/tmp/voice.mp3")
        assert build_onebot_message(_message(local)) == [{"type": "record", "data": {"file": "file:///tmp/voice.mp3"}}]

    def test_attachment_without_a_source_cannot_be_sent(self) -> None:
        assert can_send_media(MediaAttachment(media_type=MediaType.IMAGE)) is False
        assert build_onebot_message(_message(MediaAttachment(media_type=MediaType.IMAGE))) == []

    def test_documents_cannot_be_sent(self) -> None:
        assert can_send_media(_document()) is False
