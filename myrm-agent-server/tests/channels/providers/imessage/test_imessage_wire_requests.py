"""What iMessage sends to BlueBubbles for a text, an attachment and a Tapback, byte for byte where it matters.

A fake BlueBubbles records every request, so the tests pin the endpoint, the ``password`` query parameter, the JSON
and multipart fields, the timeout and how a refusal or a transport failure surfaces: the contract the real server
sees, independent of how the channel builds the requests.
"""

from __future__ import annotations

import json
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.media import MediaDownloadResult
from app.channels.providers.imessage import IMessageChannel
from app.channels.providers.imessage.helpers import MEDIA_TIMEOUT, SEND_TIMEOUT
from app.channels.types import MediaAttachment, MediaType, OutboundMessage

_API = "http://localhost:1234"
_PASSWORD = "test_pass"
_CHAT = "iMessage;-;+15551234567"
_URL = "https://img.example.com/photo.jpg"


class _FakeBlueBubbles:
    """Records requests and answers each with the next scripted response (the last one repeats)."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self._responses = list(responses) or [httpx.Response(200, json={"data": {"guid": "reported-1"}})]
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self._responses[min(len(self.requests), len(self._responses)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _channel(server: _FakeBlueBubbles, *, private_api: bool = False, helper: bool = False) -> IMessageChannel:
    ch = IMessageChannel(api_url=_API, password=_PASSWORD)
    ch._http = httpx.AsyncClient(transport=httpx.MockTransport(server.handle))
    ch._private_api_available = private_api
    ch._helper_connected = helper
    return ch


def _text(content: str = "hello", *, reply_to: str | None = None) -> OutboundMessage:
    return OutboundMessage(channel="imessage", recipient_id=_CHAT, content=content, user_id="U", reply_to_id=reply_to)


def _media(attachment: MediaAttachment) -> OutboundMessage:
    return OutboundMessage(channel="imessage", recipient_id=_CHAT, content="", user_id="U", media=(attachment,))


def _downloaded(data: bytes = b"jpeg", content_type: str = "image/jpeg") -> MediaDownloadResult:
    return MediaDownloadResult(success=True, data=data, content_type=content_type, error=None, url=_URL, size_bytes=len(data))


def _body(request: httpx.Request) -> dict[str, object]:
    return json.loads(request.content)


def _fields(request: httpx.Request) -> dict[str, tuple[str | None, str, bytes]]:
    """Multipart parts by field name: (filename, content type, payload)."""
    raw = b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.content
    message = BytesParser(policy=default).parsebytes(raw)
    return {
        str(part.get_param("name", header="content-disposition")): (
            part.get_filename(),
            part.get_content_type(),
            part.get_payload(decode=True),
        )
        for part in message.iter_parts()
    }


def _read_timeout(request: httpx.Request) -> float:
    return request.extensions["timeout"]["read"]


class TestTextRequest:
    @pytest.mark.asyncio
    async def test_a_text_is_posted_with_the_chat_a_temp_guid_and_the_message(self) -> None:
        server = _FakeBlueBubbles()
        await _channel(server).send(_text("hello"))

        (request,) = server.requests
        assert (request.method, request.url.path) == ("POST", "/api/v1/message/text")
        assert request.url.params["password"] == _PASSWORD
        body = _body(request)
        assert set(body) == {"chatGuid", "tempGuid", "message"}
        assert (body["chatGuid"], body["message"]) == (_CHAT, "hello")
        assert str(body["tempGuid"]).startswith("temp-")
        assert _read_timeout(request) == SEND_TIMEOUT

    @pytest.mark.asyncio
    async def test_every_send_gets_its_own_temp_guid(self) -> None:
        server = _FakeBlueBubbles()
        ch = _channel(server)
        await ch.send(_text("one"))
        await ch.send(_text("two"))
        assert len({_body(r)["tempGuid"] for r in server.requests}) == 2

    @pytest.mark.asyncio
    async def test_the_guid_bluebubbles_reports_is_returned(self) -> None:
        assert await _channel(_FakeBlueBubbles()).send(_text()) == "reported-1"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "answer",
        [
            httpx.Response(200, text="<html>"),
            httpx.Response(200, json={"data": {}}),
            httpx.Response(200, json={"data": {"guid": ""}}),
            httpx.Response(200, json={"data": "accepted"}),
        ],
    )
    async def test_an_answer_without_a_guid_leaves_delivery_unconfirmed(self, answer: httpx.Response) -> None:
        assert await _channel(_FakeBlueBubbles(answer)).send(_text()) is None


class TestReplyRequest:
    @pytest.mark.asyncio
    async def test_a_reply_quotes_the_message_through_the_private_api(self) -> None:
        server = _FakeBlueBubbles()
        await _channel(server, private_api=True, helper=True).send(_text(reply_to="msg-guid"))

        assert _body(server.requests[0]) | {"tempGuid": ""} == {
            "chatGuid": _CHAT,
            "tempGuid": "",
            "message": "hello",
            "method": "private-api",
            "selectedMessageGuid": "msg-guid",
            "partIndex": 0,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("private_api", "helper"), [(True, False), (False, True), (False, False)])
    async def test_without_a_connected_private_api_the_reply_is_a_plain_message(self, private_api: bool, helper: bool) -> None:
        server = _FakeBlueBubbles()
        await _channel(server, private_api=private_api, helper=helper).send(_text(reply_to="msg-guid"))
        assert set(_body(server.requests[0])) == {"chatGuid", "tempGuid", "message"}

    @pytest.mark.asyncio
    async def test_only_the_first_chunk_of_a_long_reply_quotes_the_message(self) -> None:
        server = _FakeBlueBubbles(
            httpx.Response(200, json={"data": {"guid": "first"}}), httpx.Response(200, json={"data": {"guid": "second"}})
        )
        guid = await _channel(server, private_api=True, helper=True).send(_text("word " * 3000, reply_to="msg-guid"))

        assert len(server.requests) == 2
        assert [_body(r).get("selectedMessageGuid") for r in server.requests] == ["msg-guid", None]
        assert guid == "second"


class TestTextFailure:
    @pytest.mark.asyncio
    async def test_a_transport_failure_is_a_retriable_send_error(self) -> None:
        server = _FakeBlueBubbles(httpx.ConnectError("bridge down"))
        with pytest.raises(ChannelSendError) as excinfo:
            await _channel(server).send(_text())
        assert str(excinfo.value).startswith("iMessage text send failed: bridge down")
        assert (excinfo.value.channel, excinfo.value.retriable) == ("imessage", True)
        assert isinstance(excinfo.value.__cause__, httpx.ConnectError)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("status", "retriable"), [(400, False), (404, False), (429, True), (503, True)])
    async def test_a_refusal_names_the_status_and_is_retriable_only_when_it_may_pass(self, status: int, retriable: bool) -> None:
        with pytest.raises(ChannelSendError) as excinfo:
            await _channel(_FakeBlueBubbles(httpx.Response(status))).send(_text())
        assert str(excinfo.value) == f"imessage rejected the message (HTTP {status})"
        assert (excinfo.value.channel, excinfo.value.status_code, excinfo.value.retriable) == ("imessage", status, retriable)


class TestAttachmentRequest:
    @pytest.mark.asyncio
    async def test_a_local_file_is_uploaded_as_multipart_under_its_own_name(self, tmp_path: Path) -> None:
        photo = tmp_path / "photo.png"
        photo.write_bytes(b"png-bytes")
        server = _FakeBlueBubbles()
        guid = await _channel(server).send(_media(MediaAttachment(media_type=MediaType.IMAGE, path=str(photo))))

        (request,) = server.requests
        assert (request.method, request.url.path) == ("POST", "/api/v1/message/attachment")
        assert request.url.params["password"] == _PASSWORD
        assert request.headers["content-type"].startswith("multipart/form-data")
        assert _read_timeout(request) == MEDIA_TIMEOUT
        fields = _fields(request)
        assert fields["chatGuid"][2] == _CHAT.encode()
        assert fields["name"][2] == b"photo.png"
        assert fields["tempGuid"][2].startswith(b"temp-")
        assert fields["attachment"] == ("photo.png", "image/png", b"png-bytes")
        assert guid == "reported-1"

    @pytest.mark.asyncio
    async def test_the_declared_type_of_a_local_file_wins_over_its_extension(self, tmp_path: Path) -> None:
        voice = tmp_path / "voice.bin"
        voice.write_bytes(b"audio")
        server = _FakeBlueBubbles()
        attachment = MediaAttachment(media_type=MediaType.AUDIO, path=str(voice), mime_type="audio/x-caf")
        await _channel(server).send(_media(attachment))
        assert _fields(server.requests[0])["attachment"][1] == "audio/x-caf"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("declared_name", "uploaded_as"), [(None, "photo.jpg"), ("holiday.jpg", "holiday.jpg")])
    async def test_a_downloaded_file_is_named_by_the_attachment_or_its_url(
        self, declared_name: str | None, uploaded_as: str
    ) -> None:
        server = _FakeBlueBubbles()
        download = AsyncMock(return_value=_downloaded())
        attachment = MediaAttachment(media_type=MediaType.IMAGE, url=_URL, filename=declared_name)
        with patch("app.channels.media.MediaDownloader.download", download):
            await _channel(server).send(_media(attachment))

        fields = _fields(server.requests[0])
        assert fields["name"][2] == uploaded_as.encode()
        assert fields["attachment"] == (uploaded_as, "image/jpeg", b"jpeg")
        assert download.await_args.args == (_URL,)
        assert download.await_args.kwargs["config"].timeout_seconds == MEDIA_TIMEOUT

    @pytest.mark.asyncio
    async def test_the_download_goes_through_the_channels_own_client(self) -> None:
        server = _FakeBlueBubbles()
        ch = _channel(server)
        downloader = MagicMock()
        downloader.download = AsyncMock(return_value=_downloaded())
        with patch("app.channels.media.MediaDownloader", return_value=downloader) as downloader_class:
            await ch.send(_media(MediaAttachment(media_type=MediaType.IMAGE, url=_URL)))
        assert downloader_class.call_args.kwargs["http_client"] is ch._http

    @pytest.mark.asyncio
    async def test_a_failed_download_falls_back_to_the_local_file(self, tmp_path: Path) -> None:
        photo = tmp_path / "photo.png"
        photo.write_bytes(b"png-bytes")
        server = _FakeBlueBubbles()
        failed = AsyncMock(
            return_value=MediaDownloadResult(success=False, data=None, content_type=None, error=None, url=_URL, size_bytes=0)
        )
        attachment = MediaAttachment(media_type=MediaType.IMAGE, url=_URL, path=str(photo))
        with patch("app.channels.media.MediaDownloader.download", failed):
            await _channel(server).send(_media(attachment))
        assert _fields(server.requests[0])["attachment"][2] == b"png-bytes"

    @pytest.mark.asyncio
    async def test_an_unreadable_attachment_sends_nothing_and_says_which_one(self) -> None:
        server = _FakeBlueBubbles()
        with pytest.raises(ChannelSendError) as excinfo:
            await _channel(server).send(_media(MediaAttachment(media_type=MediaType.IMAGE, path="/nonexistent/photo.png")))
        assert server.requests == []
        assert excinfo.value.failed_attachments == ("photo.png",)


class TestAttachmentFailure:
    @staticmethod
    async def _send_file(tmp_path: Path, server: _FakeBlueBubbles) -> ChannelSendError:
        photo = tmp_path / "photo.png"
        photo.write_bytes(b"png-bytes")
        with pytest.raises(ChannelSendError) as excinfo:
            await _channel(server).send(_media(MediaAttachment(media_type=MediaType.IMAGE, path=str(photo))))
        return excinfo.value

    @pytest.mark.asyncio
    async def test_a_transport_failure_fails_only_that_attachment(self, tmp_path: Path) -> None:
        error = await self._send_file(tmp_path, _FakeBlueBubbles(httpx.ReadTimeout("slow")))
        assert (error.accepted, error.failed_attachments) == (False, ("photo.png",))

    @pytest.mark.asyncio
    async def test_a_refusal_fails_that_attachment(self, tmp_path: Path) -> None:
        error = await self._send_file(tmp_path, _FakeBlueBubbles(httpx.Response(500)))
        assert (error.accepted, error.failed_attachments) == (False, ("photo.png",))


class TestTapbackRequest:
    @pytest.mark.asyncio
    async def test_a_tapback_names_the_chat_the_message_and_the_reaction(self) -> None:
        server = _FakeBlueBubbles(httpx.Response(200, json={}))
        await _channel(server).react_to_message(_CHAT, "msg-guid", "\U0001f44d")

        (request,) = server.requests
        assert (request.method, request.url.path) == ("POST", "/api/v1/message/react")
        assert request.url.params["password"] == _PASSWORD
        assert _body(request) == {"chatGuid": _CHAT, "selectedMessageGuid": "msg-guid", "reaction": "like"}
        assert _read_timeout(request) == SEND_TIMEOUT

    @pytest.mark.asyncio
    async def test_a_refused_tapback_names_the_status(self) -> None:
        server = _FakeBlueBubbles(httpx.Response(400, json={}))
        with pytest.raises(ChannelSendError) as excinfo:
            await _channel(server).react_to_message(_CHAT, "msg-guid", "\U0001f44d")
        assert str(excinfo.value) == "iMessage reaction failed: HTTP 400"
        assert (excinfo.value.channel, excinfo.value.status_code) == ("imessage", 400)
