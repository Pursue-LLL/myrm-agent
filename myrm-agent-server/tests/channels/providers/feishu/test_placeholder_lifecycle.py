"""A Feishu placeholder card lives its whole life through the two routes Feishu documents for it.

The placeholder is posted as a card whose config opts in to updates; the progress and the result replace it
through the card-update route. No other request is made, and a card Feishu refuses to update fails the edit so the
router can deliver the result as a new message.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.feishu import FeishuChannel
from app.channels.providers.feishu.sdk import FeishuClient
from app.channels.types import OutboundMessage

_SENT = httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}})


def _channel(respond: Callable[[httpx.Request], httpx.Response]) -> tuple[FeishuChannel, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return respond(request)

    client = FeishuClient("app", "secret")
    client._token = "tok"
    client._token_expires_at = time.monotonic() + 3600
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = FeishuChannel(app_id="app", app_secret="secret")
    channel._client = client
    return channel, seen


def _card(request: httpx.Request) -> dict[str, object]:
    return json.loads(json.loads(request.content)["content"])


def _result(content: str) -> OutboundMessage:
    return OutboundMessage(channel="feishu", recipient_id="oc_chat", content=content, user_id="u1")


@pytest.mark.asyncio
async def test_placeholder_progress_and_result_use_only_the_send_and_card_update_routes() -> None:
    channel, seen = _channel(lambda request: _SENT)

    message_id = await channel.send_placeholder("oc_chat", "Thinking...")
    assert message_id == "om_1"
    await channel.edit_message("oc_chat", message_id, "Searching the web...")
    await channel.edit_placeholder_message("oc_chat", message_id, _result("The answer"))

    assert [(r.method, r.url.path) for r in seen] == [
        ("POST", "/open-apis/im/v1/messages"),
        ("PATCH", "/open-apis/im/v1/messages/om_1"),
        ("PATCH", "/open-apis/im/v1/messages/om_1"),
    ]
    cards = [_card(r) for r in seen]
    # Feishu updates a card in place only if it declared update_multi when it was sent and in every update.
    configs = [card["config"] for card in cards]
    assert all(isinstance(config, dict) and config.get("update_multi") is True for config in configs)
    # The placeholder is made of components Feishu defines and carries no card id of its own.
    assert cards[0]["elements"] == [{"tag": "div", "text": {"tag": "lark_md", "content": "Thinking..."}}]
    assert "card_id" not in cards[0]
    assert "The answer" in json.dumps(cards[2], ensure_ascii=False)


@pytest.mark.asyncio
async def test_a_card_update_feishu_refuses_fails_the_edit() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            return httpx.Response(200, json={"code": 230054, "msg": "This message type does not support editing"})
        return _SENT

    channel, _ = _channel(respond)
    message_id = await channel.send_placeholder("oc_chat", "Thinking...")
    assert message_id == "om_1"

    with pytest.raises(ChannelSendError) as refused:
        await channel.edit_placeholder_message("oc_chat", message_id, _result("The answer"))

    assert refused.value.retriable is False
