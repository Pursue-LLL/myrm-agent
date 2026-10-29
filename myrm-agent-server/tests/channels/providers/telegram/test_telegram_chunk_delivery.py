"""Telegram text delivery: every part goes out once, and a failure part-way is a partial delivery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api import TelegramApiError
from app.channels.reliability.retry import RetryConfig
from app.channels.types import OutboundMessage
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN

_FAST = RetryConfig(max_retries=2, base_delay=0.0, max_delay=0.0, jitter=0.0)
_BUTTONS = {"inline_keyboard": [[{"text": "Open", "callback_data": "x"}]]}


def _channel(*, rich: bool) -> tuple[TelegramChannel, MagicMock]:
    """A channel on a mocked Bot API client; the second item is that client."""
    ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
    ch.retry_config = _FAST
    ch._rich_send_available = True if rich else False
    client = MagicMock()
    client.send_message = AsyncMock(side_effect=lambda chat, text, **kw: {"message_id": len(text)})
    client.send_rich_message = AsyncMock(side_effect=lambda chat, text, **kw: {"message_id": len(text)})
    ch._client = client
    return ch, client


def _message(reply_to_id: str | None = None) -> OutboundMessage:
    return OutboundMessage(channel="telegram", recipient_id="42", content="body", user_id="u1", reply_to_id=reply_to_id)


def _texts(mock: AsyncMock) -> list[str]:
    return [call.args[1] for call in mock.await_args_list]


@pytest.mark.asyncio
async def test_html_parts_each_go_out_once_with_the_quote_on_the_first_and_the_buttons_on_the_last() -> None:
    ch, client = _channel(rich=False)
    with (
        patch("app.channels.providers.telegram.outbound.render", return_value=["one", "two", "three"]),
        patch("app.channels.providers.telegram.outbound.build_inline_keyboard", return_value=_BUTTONS),
    ):
        result = await ch.send(_message(reply_to_id="7"))

    assert _texts(client.send_message) == ["one", "two", "three"]
    calls = client.send_message.await_args_list
    assert [c.kwargs["reply_to_message_id"] for c in calls] == [7, None, None]
    assert [c.kwargs["reply_markup"] for c in calls] == [None, None, _BUTTONS]
    assert result == "5"  # the id of the last part ("three")


@pytest.mark.asyncio
async def test_a_parse_error_on_a_later_part_is_resent_as_plain_text_without_resending_the_others() -> None:
    ch, client = _channel(rich=False)
    parse_error = TelegramApiError(400, "Bad Request: can't parse entities")
    ok = {"message_id": 1}
    client.send_message = AsyncMock(side_effect=[ok, parse_error, ok, ok])
    with patch("app.channels.providers.telegram.outbound.render", return_value=["one", "two", "three"]):
        await ch.send(_message())

    calls = client.send_message.await_args_list
    assert [c.args[1] for c in calls] == ["one", "two", "two", "three"]
    assert [c.kwargs.get("parse_mode") for c in calls] == [None, None, "", None]


@pytest.mark.asyncio
async def test_a_flood_limited_part_is_retried_alone_then_reported_as_a_partial_delivery() -> None:
    ch, client = _channel(rich=False)
    limited = TelegramApiError(429, "Too Many Requests", {"retry_after": 0})
    client.send_message = AsyncMock(side_effect=[{"message_id": 1}, limited, limited])
    with (
        patch("app.channels.providers.telegram.outbound.render", return_value=["one", "two", "three"]),
        pytest.raises(ChannelSendError) as exc_info,
    ):
        await ch.send(_message())

    assert _texts(client.send_message) == ["one", "two", "two"]
    assert exc_info.value.accepted is True
    assert exc_info.value.retriable is False
    assert "Delivered 1 of 3" in str(exc_info.value)


@pytest.mark.asyncio
async def test_a_later_part_with_an_unretriable_error_is_still_a_partial_delivery() -> None:
    ch, client = _channel(rich=False)
    client.send_message = AsyncMock(side_effect=[{"message_id": 1}, TelegramApiError(403, "Forbidden: bot was blocked")])
    with (
        patch("app.channels.providers.telegram.outbound.render", return_value=["one", "two"]),
        pytest.raises(ChannelSendError) as exc_info,
    ):
        await ch.send(_message())

    assert _texts(client.send_message) == ["one", "two"]
    assert exc_info.value.accepted is True


@pytest.mark.asyncio
async def test_the_first_html_part_failing_is_raised_as_it_is_for_the_bus_to_retry() -> None:
    ch, client = _channel(rich=False)
    client.send_message = AsyncMock(side_effect=TelegramApiError(502, "Bad Gateway"))
    with patch("app.channels.providers.telegram.outbound.render", return_value=["one", "two"]):
        with pytest.raises(TelegramApiError):
            await ch.send(_message())

    assert client.send_message.await_count == 1


@pytest.mark.asyncio
async def test_a_rejected_first_rich_part_falls_back_to_html() -> None:
    ch, client = _channel(rich=True)
    client.send_rich_message = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: entity is malformed"))
    with patch("app.channels.providers.telegram.outbound.render", return_value=["one"]):
        await ch.send(_message())

    assert client.send_rich_message.await_count == 1
    assert _texts(client.send_message) == ["one"]


@pytest.mark.asyncio
async def test_a_missing_rich_method_is_remembered_and_falls_back_to_html() -> None:
    ch, client = _channel(rich=True)
    client.send_rich_message = AsyncMock(side_effect=TelegramApiError(404, "Not Found"))
    with patch("app.channels.providers.telegram.outbound.render", return_value=["one"]):
        await ch.send(_message())

    assert ch._rich_send_available is False
    assert _texts(client.send_message) == ["one"]


@pytest.mark.asyncio
async def test_a_later_rich_part_rejected_is_a_partial_delivery_not_a_silent_truncation() -> None:
    ch, client = _channel(rich=True)
    rejected = TelegramApiError(400, "Bad Request: entity is malformed")
    client.send_rich_message = AsyncMock(side_effect=[{"message_id": 1}, rejected])
    with (
        patch("app.channels.providers.telegram.outbound.render", return_value=["body"]),
        patch("app.channels.providers.telegram.html_converter.split_markdown_rich", return_value=["a", "b", "c"]),
        pytest.raises(ChannelSendError) as exc_info,
    ):
        await ch.send(_message())

    client.send_message.assert_not_awaited()  # no HTML fallback that would resend part one
    assert exc_info.value.accepted is True
    assert "Delivered 1 of 3" in str(exc_info.value)
