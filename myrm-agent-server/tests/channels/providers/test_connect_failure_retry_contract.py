"""A connection that could not be opened is retried by the bus on every provider, however its errors surface.

Nothing left the process, so a retry cannot show the reply twice. Each channel is driven through its real HTTP
client over ``httpx.MockTransport`` and the real message bus: Slack and DingTalk let the ``httpx`` error
through, LINE wraps it in a ``ChannelSendError``, Telegram's client lets it through as well. The number of
attempts must not depend on which of these a provider does, and a request that may have reached the platform is
sent once.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.dingtalk.channel import DingTalkChannel
from app.channels.providers.line.channel import LINEChannel
from app.channels.providers.slack.channel import SlackChannel
from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api import TelegramClient
from app.channels.reliability.retry import RetryConfig
from app.channels.types import OutboundMessage
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN

_RETRY = RetryConfig(max_retries=3, base_delay=0.0, max_delay=0.0, jitter=0.0)


def _slack(http: httpx.AsyncClient) -> BaseChannel:
    channel = SlackChannel(bot_token="xoxb-test")
    channel._api._http = http
    return channel


def _dingtalk(http: httpx.AsyncClient) -> BaseChannel:
    channel = DingTalkChannel(app_key="key", app_secret="secret")
    channel._api._http = http
    return channel


def _line(http: httpx.AsyncClient) -> BaseChannel:
    channel = LINEChannel(channel_access_token="token", channel_secret="secret")
    channel._api._http = http
    return channel


def _telegram(http: httpx.AsyncClient) -> BaseChannel:
    channel = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
    channel._rich_send_available = False
    client = TelegramClient(FAKE_TELEGRAM_BOT_TOKEN)
    client._http = http
    channel._client = client
    return channel


_PROVIDERS: dict[str, Callable[[httpx.AsyncClient], BaseChannel]] = {
    "slack": _slack,
    "dingtalk": _dingtalk,
    "line": _line,
    "telegram": _telegram,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("build", _PROVIDERS.values(), ids=_PROVIDERS)
async def test_a_connection_that_cannot_be_opened_is_attempted_as_often_as_the_retry_policy_allows(
    build: Callable[[httpx.AsyncClient], BaseChannel],
) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        raise httpx.ConnectError("down", request=request)

    channel = build(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    channel.retry_config = _RETRY
    bus = MessageBus()
    bus.register_channel(channel)

    with pytest.raises((httpx.ConnectError, ChannelSendError)):
        await bus.send_now(OutboundMessage(channel=channel.name, recipient_id="42", content="hello", user_id="u1"))

    assert len(requests) == _RETRY.max_retries


# What each platform answers once the connection opens, and the message id the reply is then known by.
_ANSWERS: dict[str, tuple[dict[str, object], str]] = {
    "slack": ({"ok": True, "ts": "1730000000.000100", "channel": "C1"}, "1730000000.000100"),
    "telegram": ({"ok": True, "result": {"message_id": 7}}, "7"),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", _ANSWERS)
async def test_a_reply_is_delivered_once_the_connection_opens_on_a_later_attempt(name: str) -> None:
    answer, message_id = _ANSWERS[name]
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if len(requests) == 1:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json=answer)

    channel = _PROVIDERS[name](httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    channel.retry_config = _RETRY
    bus = MessageBus()
    bus.register_channel(channel)

    delivered = await bus.send_now(OutboundMessage(channel=channel.name, recipient_id="42", content="hello", user_id="u1"))

    assert delivered == message_id
    assert len(requests) == 2


# Providers whose client lets the ``httpx`` error through, so what the bus sees is what the platform did.
_RAW_ERROR_PROVIDERS = ("slack", "dingtalk", "telegram")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", _RAW_ERROR_PROVIDERS)
async def test_a_request_that_may_have_reached_the_platform_is_sent_once(name: str) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host or "")
        raise httpx.ReadTimeout("slow", request=request)

    channel = _PROVIDERS[name](httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    channel.retry_config = _RETRY
    bus = MessageBus()
    bus.register_channel(channel)

    with pytest.raises(httpx.ReadTimeout):
        await bus.send_now(OutboundMessage(channel=channel.name, recipient_id="42", content="hello", user_id="u1"))

    assert len(requests) == 1
