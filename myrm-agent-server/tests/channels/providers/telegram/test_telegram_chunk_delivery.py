"""Telegram text delivery: every part goes out once, and a failure part-way is a partial delivery."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api import TelegramApiError, TelegramClient
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


def _wire_channel(handler: Callable[[httpx.Request], httpx.Response]) -> TelegramChannel:
    """A channel whose real Bot API client answers from ``handler`` instead of the network."""
    ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
    ch.retry_config = _FAST
    ch._rich_send_available = True
    client = TelegramClient(FAKE_TELEGRAM_BOT_TOKEN, api_base="http://bot-api.test")
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ch._client = client
    return ch


def _message(reply_to_id: str | None = None) -> OutboundMessage:
    return OutboundMessage(channel="telegram", recipient_id="42", content="body", user_id="u1", reply_to_id=reply_to_id)


def _texts(mock: AsyncMock) -> list[str]:
    return [call.args[1] for call in mock.await_args_list]


@contextmanager
def _rich_reply(chunks: list[str], parts_of: dict[str, list[str]] | None = None) -> Iterator[None]:
    """The rich path sees ``chunks`` as the rendered reply; a chunk splits into ``parts_of[chunk]`` or stays one part."""
    with (
        patch("app.channels.providers.telegram.outbound_rich.render", return_value=chunks),
        patch(
            "app.channels.providers.telegram.html_converter.split_markdown_rich",
            side_effect=lambda text: (parts_of or {}).get(text, [text]),
        ),
    ):
        yield


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


@pytest.mark.asyncio
async def test_a_flood_limited_chunk_after_the_first_rich_chunk_is_retried_alone_and_the_order_holds() -> None:
    ch, client = _channel(rich=True)
    limited = TelegramApiError(429, "Too Many Requests", {"retry_after": 0})
    client.send_rich_message = AsyncMock(side_effect=[{"message_id": 1}, limited, {"message_id": 2}, {"message_id": 3}])
    with _rich_reply(["one", "two", "three"]):
        result = await ch.send(_message())

    assert _texts(client.send_rich_message) == ["one", "two", "two", "three"]
    assert result == "3"
    client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_chunk_after_the_first_rich_chunk_refused_for_good_ends_the_reply_without_a_hole() -> None:
    ch, client = _channel(rich=True)
    client.send_rich_message = AsyncMock(side_effect=[{"message_id": 1}, TelegramApiError(403, "Forbidden: bot was blocked")])
    with _rich_reply(["one", "two", "three"]), pytest.raises(ChannelSendError) as exc_info:
        await ch.send(_message())

    assert _texts(client.send_rich_message) == ["one", "two"]
    assert exc_info.value.accepted is True
    assert "Delivered 1 of 3" in str(exc_info.value)


@pytest.mark.asyncio
async def test_a_transport_error_after_the_first_rich_chunk_is_a_partial_delivery() -> None:
    ch, client = _channel(rich=True)
    client.send_rich_message = AsyncMock(side_effect=[{"message_id": 1}, httpx.ConnectError("down")])
    with _rich_reply(["one", "two"]), pytest.raises(ChannelSendError) as exc_info:
        await ch.send(_message())

    assert _texts(client.send_rich_message) == ["one", "two"]
    assert exc_info.value.accepted is True


@pytest.mark.asyncio
async def test_a_connection_reset_after_the_first_rich_chunk_is_retried_alone_not_resent_whole() -> None:
    ch, client = _channel(rich=True)
    client.send_rich_message = AsyncMock(side_effect=[{"message_id": 1}, OSError("reset"), {"message_id": 2}])
    with _rich_reply(["one", "two"]):
        await ch.send(_message())

    assert _texts(client.send_rich_message) == ["one", "two", "two"]


@pytest.mark.asyncio
async def test_the_rich_quote_rides_the_first_part_and_the_buttons_the_last_part_of_the_whole_reply() -> None:
    ch, client = _channel(rich=True)
    with (
        _rich_reply(["one", "two"], {"one": ["one-a", "one-b"]}),
        patch("app.channels.providers.telegram.outbound.build_inline_keyboard", return_value=_BUTTONS),
    ):
        await ch.send(_message(reply_to_id="7"))

    calls = client.send_rich_message.await_args_list
    assert _texts(client.send_rich_message) == ["one-a", "one-b", "two"]
    assert [c.kwargs["reply_to_message_id"] for c in calls] == [7, None, None]
    assert [c.kwargs["reply_markup"] for c in calls] == [None, None, _BUTTONS]


@pytest.mark.asyncio
async def test_on_the_wire_a_flood_limited_later_rich_chunk_is_retried_alone() -> None:
    """The real client turns the platform's 429 into the error the retry policy reads."""
    sent: list[str] = []
    flood_pending = [True]

    def handler(request: httpx.Request) -> httpx.Response:
        markdown = json.loads(request.content)["rich_message"]["markdown"]
        sent.append(markdown)
        if markdown == "two" and flood_pending:
            flood_pending.clear()
            body = {"ok": False, "error_code": 429, "description": "Too Many Requests", "parameters": {"retry_after": 0}}
            return httpx.Response(429, json=body)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})

    with _rich_reply(["one", "two", "three"]):
        result = await _wire_channel(handler).send(_message())

    assert sent == ["one", "two", "two", "three"]
    assert result == "4"


@pytest.mark.asyncio
async def test_on_the_wire_a_dropped_connection_on_a_later_rich_chunk_is_a_partial_delivery() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        markdown = json.loads(request.content)["rich_message"]["markdown"]
        sent.append(markdown)
        if markdown == "two":
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})

    with _rich_reply(["one", "two", "three"]), pytest.raises(ChannelSendError) as exc_info:
        await _wire_channel(handler).send(_message())

    assert sent == ["one", "two"]
    assert exc_info.value.accepted is True
    assert "Delivered 1 of 3" in str(exc_info.value)
