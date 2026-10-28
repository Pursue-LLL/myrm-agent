"""iMessage reads an attachment as ``application/octet-stream`` when nothing names its type, and marks a chat read only when it has one."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.media import MediaDownloadResult
from app.channels.providers.imessage import IMessageChannel
from app.channels.types import InboundMessage, MediaAttachment, MediaType, OutboundMessage

URL = "https://img.example.com/1.bin"


def _channel() -> IMessageChannel:
    return IMessageChannel(api_url="http://localhost:1234", password="secret")


def _download(content_type: str | None) -> AsyncMock:
    return AsyncMock(
        return_value=MediaDownloadResult(
            success=True,
            data=b"bytes",
            content_type=content_type,
            error=None,
            url=URL,
            size_bytes=5,
        )
    )


async def _sent_content_type(content_type: str | None, declared: str | None = None) -> str:
    ch = _channel()
    post = AsyncMock(return_value=httpx.Response(200, json={"data": {"guid": "g1"}}))
    media = MediaAttachment(media_type=MediaType.DOCUMENT, url=URL, mime_type=declared)
    with (
        patch.object(ch._http, "post", post),
        patch("app.channels.media.MediaDownloader.download", _download(content_type)),
    ):
        await ch.send(OutboundMessage(channel="imessage", recipient_id="chat1", content="", user_id="U", media=(media,)))
    _, _, mime = post.await_args.kwargs["files"]["attachment"]
    return mime


class TestAttachmentContentType:
    @pytest.mark.asyncio
    async def test_the_downloaded_type_is_used(self) -> None:
        assert await _sent_content_type("image/png") == "image/png"

    @pytest.mark.asyncio
    async def test_the_declared_type_wins_over_the_downloaded_one(self) -> None:
        assert await _sent_content_type("image/png", declared="image/jpeg") == "image/jpeg"

    @pytest.mark.asyncio
    async def test_an_unnamed_type_is_sent_as_a_binary_stream(self) -> None:
        assert await _sent_content_type(None) == "application/octet-stream"


class TestMarkRead:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("chat_id", "marked"), [("iMessage;-;+1", True), (None, False)])
    async def test_a_chat_is_marked_read_only_when_the_message_names_one(self, chat_id: str | None, marked: bool) -> None:
        ch = _channel()
        inbound = InboundMessage(channel="imessage", sender_id="+1", content="hi", chat_id=chat_id)
        with (
            patch.object(ch, "_parse_message", return_value=inbound),
            patch.object(ch, "_emit_inbound", new_callable=AsyncMock),
            patch.object(ch, "_mark_read", new_callable=AsyncMock) as mark_read,
        ):
            await ch.handle_webhook({"type": "new-message", "data": {}})
            await asyncio.sleep(0)
        assert mark_read.called is marked
