"""A connection that could not be opened is retried by the bus on every provider, however its errors surface.

Nothing left the process, so a retry cannot show the reply twice; a request that may have reached the platform
(a timeout while waiting for the answer, a reset) is sent once. Each channel is driven through its real HTTP
client over ``httpx.MockTransport`` and the real message bus: Slack, DingTalk and Telegram let the ``httpx``
error through, the others wrap it in a ``ChannelSendError``. The number of attempts must not depend on which of
these a provider does.
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
from app.channels.providers.signal.channel import SignalChannel
from app.channels.providers.slack.channel import SlackChannel
from app.channels.providers.sms import SMSChannel
from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api import TelegramClient
from app.channels.providers.zalo import ZaloChannel
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


def _sms(http: httpx.AsyncClient) -> BaseChannel:
    channel = SMSChannel(account_sid="AC123", auth_token="token", phone_number="+15551234567")
    channel._client = http
    return channel


def _zalo(http: httpx.AsyncClient) -> BaseChannel:
    channel = ZaloChannel(access_token="token")
    channel._http = http
    return channel


def _signal(http: httpx.AsyncClient) -> BaseChannel:
    channel = SignalChannel(api_url="http://signal:8080", phone_number="+15551234567")
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
    "sms": _sms,
    "zalo": _zalo,
    "signal": _signal,
}

# The providers that turn the ``httpx`` error into a ``ChannelSendError`` and so decide its retriability themselves.
_WRAPPING_PROVIDERS = ("line", "sms", "zalo", "signal")


async def _requests_made_while_failing_with(
    build: Callable[[httpx.AsyncClient], BaseChannel], error_type: type[httpx.RequestError]
) -> int:
    """Send one message through the real bus while every request raises ``error_type``; return the request count."""
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        raise error_type("failing", request=request)

    channel = build(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    channel.retry_config = _RETRY
    bus = MessageBus()
    bus.register_channel(channel)

    with pytest.raises((httpx.RequestError, ChannelSendError)):
        await bus.send_now(OutboundMessage(channel=channel.name, recipient_id="42", content="hello", user_id="u1"))
    return len(requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("build", _PROVIDERS.values(), ids=_PROVIDERS)
async def test_a_connection_that_cannot_be_opened_is_attempted_as_often_as_the_retry_policy_allows(
    build: Callable[[httpx.AsyncClient], BaseChannel],
) -> None:
    assert await _requests_made_while_failing_with(build, httpx.ConnectError) == _RETRY.max_retries


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


@pytest.mark.asyncio
@pytest.mark.parametrize("build", _PROVIDERS.values(), ids=_PROVIDERS)
@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.WriteTimeout, httpx.ReadError, httpx.RemoteProtocolError])
async def test_a_request_that_may_have_reached_the_platform_is_sent_once(
    build: Callable[[httpx.AsyncClient], BaseChannel], error_type: type[httpx.RequestError]
) -> None:
    assert await _requests_made_while_failing_with(build, error_type) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("name", _WRAPPING_PROVIDERS)
@pytest.mark.parametrize("error_type", [httpx.ConnectTimeout, httpx.PoolTimeout, httpx.ProxyError])
async def test_a_wrapped_request_that_never_left_is_retried(name: str, error_type: type[httpx.RequestError]) -> None:
    assert await _requests_made_while_failing_with(_PROVIDERS[name], error_type) == _RETRY.max_retries
