"""Signal outbound: every chunk reaches signal-cli, and what does not arrive is reported."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.signal import SignalChannel
from app.channels.types import MediaAttachment, MediaType, OutboundMessage


def _channel(*timestamps: int, status: int = 201) -> SignalChannel:
    ch = SignalChannel(api_url="http://signal:8080", phone_number="+1234567890")
    responses = []
    for ts in timestamps or (1,):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = {"timestamp": ts}
        responses.append(resp)
    ch._api._http.post = AsyncMock(side_effect=responses)  # type: ignore[assignment]
    return ch


def _message(*media: MediaAttachment, content: str = "") -> OutboundMessage:
    return OutboundMessage(channel="signal", user_id="u1", recipient_id="+9999", content=content, media=media)


def _file(tmp_path: Path, name: str = "report.pdf") -> MediaAttachment:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4 body")
    return MediaAttachment(media_type=MediaType.DOCUMENT, path=str(path), mime_type="application/pdf")


def _payloads(ch: SignalChannel) -> list[dict[str, object]]:
    return [call.kwargs["json"] for call in ch._api._http.post.await_args_list]


class TestChunks:
    @pytest.mark.asyncio
    async def test_every_chunk_is_posted_and_the_first_timestamp_is_returned(self) -> None:
        ch = _channel(111, 222)
        with patch("app.channels.providers.signal.channel.render", return_value=["one", "two"]):
            result = await ch.send(_message(content="long text"))

        assert result == "111"
        assert [p["message"] for p in _payloads(ch)] == ["one", "two"]

    @pytest.mark.asyncio
    async def test_attachments_ride_with_the_first_chunk_only(self, tmp_path: Path) -> None:
        ch = _channel(111, 222)
        with patch("app.channels.providers.signal.channel.render", return_value=["one", "two"]):
            await ch.send(_message(_file(tmp_path), content="long text"))

        first, second = _payloads(ch)
        assert len(first["base64_attachments"]) == 1
        assert "base64_attachments" not in second

    @pytest.mark.asyncio
    async def test_files_only_message_is_one_empty_text_request(self, tmp_path: Path) -> None:
        ch = _channel(333)
        result = await ch.send(_message(_file(tmp_path)))

        assert result == "333"
        (payload,) = _payloads(ch)
        assert payload["message"] == ""
        assert payload["base64_attachments"][0].startswith("data:application/pdf;filename=file;base64,")

    @pytest.mark.asyncio
    async def test_a_201_without_a_timestamp_still_counts_as_sent(self) -> None:
        ch = _channel()
        ch._api._http.post.side_effect = None
        ch._api._http.post.return_value = MagicMock(status_code=201, json=MagicMock(side_effect=ValueError("not json")))

        assert await ch.send(_message(content="hi")) is None


class TestFailures:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("status", "retriable"), [(500, True), (429, True), (400, False), (404, False)])
    async def test_rejection_is_classified_by_status(self, status: int, retriable: bool) -> None:
        ch = _channel(status=status)
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(content="hi"))

        assert exc_info.value.retriable is retriable
        assert exc_info.value.accepted is False

    @pytest.mark.asyncio
    async def test_unreadable_file_is_dropped_but_the_rest_goes_out(self, tmp_path: Path) -> None:
        ch = _channel(444)
        missing = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "gone.pdf"))
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(missing, _file(tmp_path), content="Report"))

        (payload,) = _payloads(ch)
        assert len(payload["base64_attachments"]) == 1
        assert exc_info.value.accepted is True
        assert exc_info.value.failed_attachments == ("gone.pdf",)

    @pytest.mark.asyncio
    async def test_nothing_encodable_and_no_text_sends_nothing(self, tmp_path: Path) -> None:
        ch = _channel()
        missing = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "gone.pdf"))
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(missing))

        ch._api._http.post.assert_not_awaited()
        assert exc_info.value.accepted is False
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_empty_file_is_a_permanent_failure(self, tmp_path: Path) -> None:
        ch = _channel()
        empty = tmp_path / "empty.txt"
        empty.write_bytes(b"")
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(MediaAttachment(media_type=MediaType.DOCUMENT, path=str(empty))))

        assert exc_info.value.retriable is False
        assert exc_info.value.failed_attachments == ("empty.txt",)
