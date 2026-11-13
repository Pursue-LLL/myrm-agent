"""A reply travels router → channel → Feishu platform and ends up as exactly the messages the user should read.

The router renders the reply once, edits the placeholder card in place, and when Feishu refuses the edit it
sends the reply as a message of its own and removes the stale placeholder. The platform here follows the
documented rules: a card is updated only if both the stored card and the update opt in with ``update_multi``.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.providers.feishu import FeishuChannel
from app.channels.providers.feishu.sdk import FeishuClient
from app.channels.routing.message_effects import MessageEffects
from app.channels.types import OutboundMessage

_SOURCES = [{"url": "https://a.dev/x", "title": "Source A"}, {"url": "https://b.dev/y", "title": "Source B"}]
_COST = {"cost_usd": 0.0123, "model_name": "gpt-5", "total_tokens": 1500}


class FakeFeishu:
    """The message routes the channel uses (send, update, delete), with the platform's update rule."""

    def __init__(self, *, refuse_updates: bool = False) -> None:
        self.messages: dict[str, dict[str, object]] = {}
        self.requests: list[tuple[str, str]] = []
        self._refuse_updates = refuse_updates

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))
        message_id = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST":
            body = json.loads(request.content)
            message_id = f"om_{len(self.requests)}"
            self.messages[message_id] = {"type": body["msg_type"], "content": json.loads(body["content"])}
            return httpx.Response(200, json={"code": 0, "data": {"message_id": message_id}})
        if request.method == "PATCH":
            stored = self.messages.get(message_id)
            update = json.loads(json.loads(request.content)["content"])
            if self._refuse_updates or stored is None or not (_opts_in(stored["content"]) and _opts_in(update)):
                return httpx.Response(200, json={"code": 230054, "msg": "This message cannot be updated"})
            stored["content"] = update
            return httpx.Response(200, json={"code": 0})
        self.messages.pop(message_id, None)
        return httpx.Response(200, json={"code": 0})

    def visible_text(self) -> list[str]:
        """What the user reads in the chat, message by message."""
        return [json.dumps(message["content"], ensure_ascii=False) for message in self.messages.values()]


def _opts_in(card: object) -> bool:
    config = card.get("config") if isinstance(card, dict) else None
    return isinstance(config, dict) and config.get("update_multi") is True


def _router(platform: FakeFeishu) -> MessageEffects:
    client = FeishuClient("app", "secret")
    client._token = "tok"
    client._token_expires_at = time.monotonic() + 3600
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(platform))
    channel = FeishuChannel(app_id="app", app_secret="secret")
    channel._client = client

    async def publish(message: OutboundMessage) -> None:
        await channel.send(message)

    async def persist(message: OutboundMessage) -> OutboundMessage:
        return message

    bus = SimpleNamespace(
        get_channel=lambda name: channel,
        publish_outbound=publish,
        durable_outbound=SimpleNamespace(persist_direct_send=persist, mark_attempting=AsyncMock(), ack=AsyncMock()),
    )
    return MessageEffects(bus)  # type: ignore[arg-type]


def _reply(content: str, **metadata: object) -> OutboundMessage:
    return OutboundMessage(channel="feishu", recipient_id="oc_chat", content=content, user_id="u1", metadata=metadata or None)


async def _deliver(platform: FakeFeishu, reply: OutboundMessage) -> None:
    router = _router(platform)
    placeholder_id = await router.send_placeholder("feishu", "oc_chat")
    assert placeholder_id is not None
    await router.edit_placeholder("feishu", "oc_chat", placeholder_id, reply)


@pytest.mark.asyncio
async def test_a_short_reply_replaces_the_placeholder_and_nothing_else_is_sent() -> None:
    platform = FakeFeishu()

    await _deliver(platform, _reply("The answer"))

    assert [method for method, _ in platform.requests] == ["POST", "PATCH"]
    assert len(platform.messages) == 1
    assert "The answer" in platform.visible_text()[0]


@pytest.mark.asyncio
async def test_sources_and_cost_are_read_once_and_the_sources_are_numbered() -> None:
    platform = FakeFeishu()

    await _deliver(platform, _reply("It is so [1][2]", sources=_SOURCES, cost_metadata=_COST))

    (shown,) = platform.visible_text()
    assert shown.count("https://a.dev/x") == 1
    assert shown.count("https://b.dev/y") == 1
    assert "[1] [Source A](https://a.dev/x)" in shown
    assert "[2] [Source B](https://b.dev/y)" in shown
    assert shown.count("~$0.0123") == 1
    assert "refusesource" not in shown


@pytest.mark.asyncio
async def test_a_long_reply_is_split_without_losing_or_repeating_a_line_and_its_sources_come_once() -> None:
    platform = FakeFeishu()
    lines = [f"line-{n:04d} " + "x" * 60 for n in range(150)]

    await _deliver(platform, _reply("\n".join(lines), sources=_SOURCES))

    shown = "\n".join(platform.visible_text())
    assert len(platform.messages) > 1
    assert [shown.count(line.split()[0]) for line in lines] == [1] * len(lines)
    assert shown.count("https://a.dev/x") == 1


@pytest.mark.asyncio
async def test_a_reply_feishu_will_not_take_as_an_edit_arrives_once_and_the_placeholder_is_removed() -> None:
    platform = FakeFeishu(refuse_updates=True)

    await _deliver(platform, _reply("The answer", sources=_SOURCES))

    assert [method for method, _ in platform.requests] == ["POST", "PATCH", "POST", "DELETE"]
    (shown,) = platform.visible_text()
    assert "The answer" in shown
    assert shown.count("https://a.dev/x") == 1
    assert "Thinking" not in shown
