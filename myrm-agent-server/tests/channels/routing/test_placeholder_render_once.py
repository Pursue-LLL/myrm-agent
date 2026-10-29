"""The placeholder edit renders a reply once: the channel that receives it must not decorate it again."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.providers.slack import SlackChannel
from app.channels.providers.telegram import TelegramChannel
from app.channels.reliability.retry import RetryConfig
from app.channels.rendering.renderer import render
from app.channels.routing.message_effects import MessageEffects
from app.channels.types import OutboundMessage, RenderStyle, ToolStep, ToolSummaryDisplay
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN

_STEPS = (ToolStep(name="web_search", label="Searched the web"), ToolStep(name="bash", label="Ran code"))
_SUMMARY = "Searched the web → Ran code"


def _reply(channel: str, content: str = "Done: R&D report ready.") -> OutboundMessage:
    return OutboundMessage(channel=channel, recipient_id="C1", content=content, user_id="u1", tool_steps=_STEPS)


def _bus(channel: object) -> MagicMock:
    async def _persist(msg: OutboundMessage) -> OutboundMessage:
        return msg

    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=channel)
    bus.publish_outbound = AsyncMock()
    bus.durable_outbound.persist_direct_send = AsyncMock(side_effect=_persist)
    bus.durable_outbound.mark_attempting = AsyncMock()
    bus.durable_outbound.ack = AsyncMock()
    return bus


def _published(bus: MagicMock) -> list[OutboundMessage]:
    return [call.args[0] for call in bus.publish_outbound.await_args_list]


def _slack() -> SlackChannel:
    channel = SlackChannel(bot_token="xoxb-test", app_token="xapp-test")
    channel._bot_user_id = "U_BOT"
    channel._team_id = "T_TEAM"
    return channel


def _slack_calls(post: AsyncMock, method: str) -> list[dict[str, object]]:
    return [call.kwargs["json"] for call in post.await_args_list if str(call.args[0]).endswith(f"/{method}")]


class TestSlackFinalReply:
    @pytest.mark.asyncio
    async def test_a_reply_edited_in_place_carries_the_summary_once(self) -> None:
        channel = _slack()
        reply = _reply("slack")
        rendered = render(reply, channel.render_style)[0]
        post = AsyncMock(return_value=httpx.Response(200, json={"ok": True}))

        with patch.object(channel._api._http, "post", post):
            await MessageEffects(_bus(channel)).edit_placeholder("slack", "C1", "9.9", reply)

        (update,) = _slack_calls(post, "chat.update")
        assert update["text"] == rendered
        assert str(update["text"]).count(_SUMMARY) == 1

    @pytest.mark.asyncio
    async def test_a_reply_that_slack_will_not_edit_in_is_published_as_a_new_message(self) -> None:
        channel = _slack()
        reply = _reply("slack")
        bus = _bus(channel)
        rejected = AsyncMock(return_value=httpx.Response(200, json={"ok": False, "error": "cant_update_message"}))

        with patch.object(channel._api._http, "post", rejected):
            await MessageEffects(bus).edit_placeholder("slack", "C1", "9.9", reply)

        assert [message.content for message in _published(bus)] == [reply.content]

    @pytest.mark.asyncio
    async def test_a_progress_edit_that_slack_rejects_is_reported_as_failed(self) -> None:
        channel = _slack()
        rejected = AsyncMock(return_value=httpx.Response(200, json={"ok": False, "error": "message_not_found"}))

        with patch.object(channel._api._http, "post", rejected):
            assert await MessageEffects(_bus(channel)).edit_progress("slack", "C1", "9.9", "Searching") is False

    @pytest.mark.asyncio
    async def test_a_reply_posted_normally_is_still_decorated_once(self) -> None:
        channel = _slack()
        post = AsyncMock(return_value=httpx.Response(200, json={"ok": True, "ts": "2.2"}))

        with patch.object(channel._api._http, "post", post):
            await channel.send(_reply("slack"))

        (posted,) = _slack_calls(post, "chat.postMessage")
        assert str(posted["text"]).count(_SUMMARY) == 1

    @pytest.mark.asyncio
    async def test_the_chunks_that_follow_the_edit_are_posted_as_rendered(self) -> None:
        channel = _slack()
        channel.render_style = RenderStyle(format="mrkdwn", max_text_length=80, tool_summary_display=ToolSummaryDisplay.COMPACT)
        bus = _bus(channel)
        post = AsyncMock(return_value=httpx.Response(200, json={"ok": True, "ts": "3.3"}))

        with patch.object(channel._api._http, "post", post):
            await MessageEffects(bus).edit_placeholder("slack", "C1", "9.9", _reply("slack", "word " * 60))
            for extra in _published(bus):
                await channel.send(extra)

        extras = _published(bus)
        assert extras
        posted = [str(body["text"]) for body in _slack_calls(post, "chat.postMessage")]
        (update,) = _slack_calls(post, "chat.update")
        assert posted == [extra.content for extra in extras]
        assert "".join([str(update["text"]), *posted]).count(_SUMMARY) == 1


class TestTelegramFinalReply:
    @pytest.mark.asyncio
    async def test_the_edited_reply_carries_the_summary_once(self) -> None:
        channel = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
        channel._rich_send_available = False
        channel._client = MagicMock()
        channel._client.edit_message_text = AsyncMock(return_value={"message_id": 100})

        await MessageEffects(_bus(channel)).edit_placeholder("telegram", "42", "100", _reply("telegram"))

        edited = channel._client.edit_message_text.await_args.args[2]
        assert edited.count(_SUMMARY) == 1


class TestWhatTheChannelReceives:
    @staticmethod
    def _recording_channel(max_text_length: int = 4096) -> MagicMock:
        channel = MagicMock()
        channel.edit_placeholder_message = AsyncMock()
        channel.retry_config = RetryConfig(max_retries=1, base_delay=0.0, jitter=0.0)
        channel.should_retry = MagicMock(return_value=False)
        channel.extract_retry_after = MagicMock(return_value=None)
        channel.render_style = RenderStyle(
            format="markdown", max_text_length=max_text_length, tool_summary_display=ToolSummaryDisplay.COMPACT
        )
        return channel

    @pytest.mark.asyncio
    async def test_the_edit_and_every_chunk_after_it_arrive_marked_rendered(self) -> None:
        channel = self._recording_channel(max_text_length=80)
        bus = _bus(channel)

        await MessageEffects(bus).edit_placeholder("test", "C1", "ph", _reply("test", "word " * 60))

        edited = channel.edit_placeholder_message.await_args.args[2]
        chunks = [edited, *_published(bus)]
        assert len(chunks) > 1
        assert all(render(chunk, channel.render_style) == [chunk.content] for chunk in chunks)

    @pytest.mark.asyncio
    async def test_a_failed_edit_falls_back_to_the_unrendered_reply(self) -> None:
        channel = self._recording_channel()
        channel.edit_placeholder_message.side_effect = RuntimeError("edit refused")
        bus = _bus(channel)
        reply = _reply("test")

        await MessageEffects(bus).edit_placeholder("test", "C1", "ph", reply)

        (fallback,) = _published(bus)
        assert fallback.content == reply.content
        assert render(fallback, channel.render_style)[0].count(_SUMMARY) == 1

    @pytest.mark.asyncio
    async def test_attachments_that_follow_keep_the_original_metadata(self) -> None:
        from tests.channels.core.outbound_testkit import make_ephemeral_doc

        doc = make_ephemeral_doc("report.pdf")
        channel = self._recording_channel()
        channel.capabilities = MagicMock(media=True, file_upload=True, buttons=True)
        bus = _bus(channel)
        reply = OutboundMessage(
            channel="test", recipient_id="C1", content="ready", user_id="u1", media=(doc,), metadata={"hook": "x"}
        )

        await MessageEffects(bus).edit_placeholder("test", "C1", "ph", reply)

        (files_only,) = _published(bus)
        assert json.dumps(files_only.metadata) == json.dumps({"hook": "x"})
