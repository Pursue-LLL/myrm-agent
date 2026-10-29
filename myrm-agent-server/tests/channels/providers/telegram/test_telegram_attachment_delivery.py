"""Telegram outbound: text first, then each attachment; what Telegram does not take is reported."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api_core import TelegramApiError
from app.channels.types import MediaAttachment, MediaType, OutboundMessage
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN


def _channel() -> tuple[TelegramChannel, MagicMock]:
    """A channel over a mocked client, returned with that client so tests can script and inspect its calls."""
    ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
    ch._rich_send_available = False
    client = MagicMock()
    client.send_message = AsyncMock(return_value={"message_id": 10})
    client.send_photo = AsyncMock(return_value={"message_id": 11})
    client.send_document = AsyncMock(return_value={"message_id": 12})
    ch._client = client
    return ch, client


def _message(*media: MediaAttachment, content: str = "") -> OutboundMessage:
    return OutboundMessage(channel="telegram", recipient_id="42", content=content, user_id="u1", media=media)


def _photo(url: str = "https://img.example.com/a.png") -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.IMAGE, url=url)


def _document(url: str = "https://files.example.com/r.pdf") -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.DOCUMENT, url=url)


class TestOrder:
    @pytest.mark.asyncio
    async def test_text_is_sent_before_the_attachments(self) -> None:
        ch, client = _channel()
        order: list[str] = []

        def record(kind: str, message_id: int) -> Callable[..., dict[str, int]]:
            def send(*args: object, **kwargs: object) -> dict[str, int]:
                order.append(kind)
                return {"message_id": message_id}

            return send

        client.send_message.side_effect = record("text", 10)
        client.send_photo.side_effect = record("photo", 11)

        result = await ch.send(_message(_photo(), content="Here it is"))

        assert order == ["text", "photo"]
        assert result == "10"

    @pytest.mark.asyncio
    async def test_attachments_only_message_returns_no_id(self) -> None:
        ch, client = _channel()
        assert await ch.send(_message(_photo())) is None
        client.send_message.assert_not_awaited()


class TestFailures:
    @pytest.mark.asyncio
    async def test_failed_attachment_is_reported_after_the_text_and_the_others(self) -> None:
        ch, client = _channel()
        client.send_photo.side_effect = TelegramApiError(400, "Bad Request: failed to get HTTP URL content")

        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(_photo("https://bad.example.com/a.png"), _document(), content="Files"))

        client.send_message.assert_awaited_once()
        client.send_document.assert_awaited_once()
        assert exc_info.value.accepted is True
        assert exc_info.value.retriable is False
        assert exc_info.value.failed_attachments == ("https://bad.example.com/a.png",)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("code", "retriable"), [(400, False), (403, False), (413, False), (429, True), (502, True)])
    async def test_telegram_rejection_is_classified_by_error_code(self, code: int, retriable: bool) -> None:
        ch, client = _channel()
        client.send_photo.side_effect = TelegramApiError(code, "rejected")

        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(_photo()))

        assert exc_info.value.retriable is retriable
        assert exc_info.value.accepted is False

    @pytest.mark.asyncio
    async def test_network_failure_is_retriable(self) -> None:
        ch, client = _channel()
        client.send_photo.side_effect = ConnectionError("reset")

        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(_message(_photo()))

        assert exc_info.value.retriable is True

    @pytest.mark.asyncio
    async def test_text_failure_still_surfaces_as_the_telegram_error(self) -> None:
        ch, client = _channel()
        client.send_message.side_effect = TelegramApiError(500, "Internal")

        with pytest.raises(TelegramApiError):
            await ch.send(_message(_photo(), content="text"))

        client.send_photo.assert_not_awaited()
