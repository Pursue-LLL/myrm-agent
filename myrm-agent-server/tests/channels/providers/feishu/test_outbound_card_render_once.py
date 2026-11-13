"""A reply is shown once: the Feishu card adds sources and cost to a reply that is not rendered, never to one that is."""

from __future__ import annotations

import dataclasses
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.feishu import FeishuChannel
from app.channels.providers.feishu.sdk import FeishuClient
from app.channels.rendering.renderer import is_rendered, mark_rendered, render
from app.channels.routing.message_effects import MessageEffects
from app.channels.types import OutboundMessage, ToolStep
from app.channels.types.components import QuickReply

_FOURTH = "https://four.example"
_FIFTH = "https://five.example"
_SOURCES = [
    {"title": "Fourth", "url": _FOURTH, "index": 4},
    {"title": "Fifth", "url": _FIFTH, "index": 5},
]
_COST = {"cost_usd": 0.005, "model_name": "gpt-4o", "total_tokens": 1200}
_COST_TEXT = "1.2k tokens"
_STEPS = (ToolStep(name="web_search", label="Searched the web"),)
# 30 paragraphs of ~330 chars: well past Feishu's 4000-char render limit, so the router must split the reply.
_LONG_BODY = "\n\n".join(
    f"Paragraph {i}: " + "Claim 【4】 and claim 【5】 are supported by the retrieved pages. " * 4 for i in range(30)
)


def _reply(content: str = "Claim A 【4】 and claim B 【5】.", **metadata: object) -> OutboundMessage:
    return OutboundMessage(
        channel="feishu",
        recipient_id="oc_chat1",
        content=content,
        user_id="u1",
        tool_steps=_STEPS,
        metadata={"sources": _SOURCES, "cost_metadata": _COST, **metadata},
    )


def _channel() -> tuple[FeishuChannel, AsyncMock]:
    channel = FeishuChannel(app_id="test_app_id", app_secret="test_app_secret")
    client = AsyncMock(spec=FeishuClient)
    client.update_card.return_value = True
    client.send_message.return_value = "om_1"
    channel._client = client
    return channel, client


def _bus(channel: FeishuChannel, published: list[OutboundMessage]) -> MagicMock:
    async def _persist(msg: OutboundMessage) -> OutboundMessage:
        return msg

    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=channel)
    bus.publish_outbound = AsyncMock(side_effect=published.append)
    bus.durable_outbound.persist_direct_send = AsyncMock(side_effect=_persist)
    bus.durable_outbound.mark_attempting = AsyncMock()
    bus.durable_outbound.ack = AsyncMock()
    return bus


def _card_text(card_json: str) -> str:
    """Everything a reader sees in the card: markdown blocks and the note line."""
    parts: list[str] = []
    for element in json.loads(card_json)["elements"]:
        if isinstance(element.get("text"), dict):
            parts.append(str(element["text"]["content"]))
        elif element.get("tag") == "note":
            parts.extend(str(part.get("content")) for part in element.get("elements", []))
    return "\n".join(parts)


async def _sent_card_texts(channel: FeishuChannel, client: AsyncMock, messages: list[OutboundMessage]) -> list[str]:
    texts: list[str] = []
    for message in messages:
        client.send_message.reset_mock()
        await channel.send(message)
        texts.extend(_card_text(call.args[2]) for call in client.send_message.await_args_list)
    return texts


class TestRenderedReply:
    @pytest.mark.asyncio
    async def test_a_reply_edited_into_the_placeholder_shows_sources_and_cost_once(self) -> None:
        channel, client = _channel()

        await MessageEffects(_bus(channel, [])).edit_placeholder("feishu", "oc_chat1", "ph-1", _reply())

        shown = _card_text(client.update_card.await_args.args[1])
        assert shown.count(_FOURTH) == 1
        assert shown.count(_FIFTH) == 1
        assert shown.count(_COST_TEXT) == 1

    @pytest.mark.asyncio
    async def test_a_split_reply_shows_sources_and_cost_once_across_its_messages(self) -> None:
        channel, client = _channel()
        published: list[OutboundMessage] = []

        await MessageEffects(_bus(channel, published)).edit_placeholder("feishu", "oc_chat1", "ph-1", _reply(_LONG_BODY))
        shown = [_card_text(client.update_card.await_args.args[1])]
        shown += await _sent_card_texts(channel, client, published)

        assert len(shown) > 1, "the reply must be long enough to be split, or this test proves nothing"
        assert sum(text.count(_FOURTH) for text in shown) == 1
        assert sum(text.count(_COST_TEXT) for text in shown) == 1

    @pytest.mark.asyncio
    async def test_a_rendered_reply_published_as_a_new_message_shows_sources_and_cost_once(self) -> None:
        channel, client = _channel()
        reply = _reply()
        rendered = mark_rendered(reply, render(reply, channel.render_style)[0])

        (shown,) = await _sent_card_texts(channel, client, [rendered])

        assert shown.count(_FOURTH) == 1
        assert shown.count(_COST_TEXT) == 1

    @pytest.mark.asyncio
    async def test_a_rendered_reply_keeps_its_quick_reply_buttons(self) -> None:
        channel, client = _channel()
        reply = dataclasses.replace(_reply(), quick_replies=(QuickReply(label="Go on", text="continue"),))
        rendered = mark_rendered(reply, render(reply, channel.render_style)[0])

        await channel.edit_placeholder_message("oc_chat1", "ph-1", rendered)

        card = json.loads(client.update_card.await_args.args[1])
        buttons = [button for element in card["elements"] if element.get("tag") == "action" for button in element["actions"]]
        assert [button["text"]["content"] for button in buttons] == ["Go on"]

    def test_only_a_marked_message_counts_as_rendered(self) -> None:
        reply = _reply()

        assert not is_rendered(reply)
        assert not is_rendered(OutboundMessage(channel="feishu", recipient_id="oc_chat1", content="x", user_id="u1"))
        assert is_rendered(mark_rendered(reply, "chunk"))


class TestUnrenderedReply:
    @pytest.mark.asyncio
    async def test_the_card_numbers_sources_like_the_citations_in_the_text(self) -> None:
        channel, client = _channel()

        (shown,) = await _sent_card_texts(channel, client, [_reply()])

        assert f"[4] [Fourth]({_FOURTH})" in shown
        assert f"[5] [Fifth]({_FIFTH})" in shown
        assert "**Sources**" in shown
        assert "refusesource" not in shown
        assert shown.count(_COST_TEXT) == 1

    @pytest.mark.asyncio
    async def test_a_source_without_an_index_is_numbered_by_its_position(self) -> None:
        channel, client = _channel()
        reply = _reply(sources=[{"title": "First", "url": _FOURTH}, {"title": "Second", "url": _FIFTH}])

        (shown,) = await _sent_card_texts(channel, client, [reply])

        assert f"[1] [First]({_FOURTH})" in shown
        assert f"[2] [Second]({_FIFTH})" in shown

    @pytest.mark.asyncio
    async def test_a_source_without_a_url_keeps_its_position_in_the_numbering(self) -> None:
        channel, client = _channel()
        reply = _reply(sources=[{"title": "No link"}, {"title": "Second", "url": _FIFTH}])

        (shown,) = await _sent_card_texts(channel, client, [reply])

        assert f"[2] [Second]({_FIFTH})" in shown
        assert "No link" not in shown
