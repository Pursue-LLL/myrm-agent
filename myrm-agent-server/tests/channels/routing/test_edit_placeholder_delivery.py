"""Placeholder edit path: text edits the placeholder, attachments follow through the bus, nothing is lost."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.reliability.retry import RetryConfig
from app.channels.routing.message_effects import MessageEffects
from app.channels.types import ActionButton, ChannelCapabilities, OutboundMessage, RenderStyle
from tests.channels.core.outbound_testkit import make_ephemeral_doc


def _channel(*, media: bool = True, max_text_length: int = 4096) -> MagicMock:
    channel = MagicMock()
    channel.edit_placeholder_message = AsyncMock()
    channel.retry_config = RetryConfig(max_retries=1, base_delay=0.0, jitter=0.0)
    channel.should_retry = MagicMock(return_value=False)
    channel.extract_retry_after = MagicMock(return_value=None)
    channel.capabilities = ChannelCapabilities(media=media, file_upload=media, buttons=True)
    channel.render_style = RenderStyle(format="markdown", max_text_length=max_text_length)
    return channel


def _bus(channel: MagicMock) -> MagicMock:
    async def _persist(msg: OutboundMessage) -> OutboundMessage:
        return msg

    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=channel)
    bus.publish_outbound = AsyncMock()
    bus.durable_outbound.persist_direct_send = AsyncMock(side_effect=_persist)
    bus.durable_outbound.mark_attempting = AsyncMock()
    bus.durable_outbound.ack = AsyncMock()
    return bus


def _reply(content: str, **overrides: object) -> OutboundMessage:
    return OutboundMessage(channel="test", recipient_id="chat-1", content=content, user_id="u1", **overrides)  # type: ignore[arg-type]


def _published(bus: MagicMock) -> list[OutboundMessage]:
    return [call.args[0] for call in bus.publish_outbound.await_args_list]


def _edited(channel: MagicMock) -> OutboundMessage:
    return channel.edit_placeholder_message.await_args.args[2]


class TestAttachmentsFollowTheEdit:
    @pytest.mark.asyncio
    async def test_files_go_out_as_a_message_of_their_own(self) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = _channel()
        bus = _bus(channel)

        await MessageEffects(bus).edit_placeholder("test", "chat-1", "ph-1", _reply("Report ready", media=(doc,)))

        assert _edited(channel).content == "Report ready"
        assert _edited(channel).media == ()
        (follow_up,) = _published(bus)
        assert (follow_up.content, follow_up.media, follow_up.components) == ("", (doc,), ())
        Path(doc.path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_follow_up_keeps_routing_metadata(self) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = _channel()
        bus = _bus(channel)
        reply = _reply("Report ready", media=(doc,), metadata={"webhookUrl": "https://hook.example/1"})

        await MessageEffects(bus).edit_placeholder("test", "chat-1", "ph-1", reply)

        (follow_up,) = _published(bus)
        assert follow_up.metadata == {"webhookUrl": "https://hook.example/1"}
        Path(doc.path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_extra_text_chunks_do_not_repeat_attachments_or_buttons(self) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = _channel(max_text_length=20)
        bus = _bus(channel)
        button = ActionButton(label="Open", action_id="open")
        reply = _reply("alpha beta gamma delta epsilon zeta eta theta", media=(doc,), components=((button,),))

        await MessageEffects(bus).edit_placeholder("test", "chat-1", "ph-1", reply)

        *text_chunks, files_only = _published(bus)
        assert text_chunks
        assert all(chunk.media == () and chunk.components == () and chunk.content for chunk in text_chunks)
        assert files_only.media == (doc,)
        assert files_only.content == ""
        Path(doc.path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_reply_without_attachments_is_a_single_edit(self) -> None:
        channel = _channel()
        bus = _bus(channel)

        await MessageEffects(bus).edit_placeholder("test", "chat-1", "ph-1", _reply("Just text"))

        assert _edited(channel).content == "Just text"
        bus.publish_outbound.assert_not_awaited()


class TestWhenTheEditCannotCarryTheReply:
    @pytest.mark.asyncio
    async def test_failed_edit_publishes_the_complete_reply_with_its_attachments(self) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = _channel()
        channel.edit_placeholder_message.side_effect = ChannelSendError("placeholder gone", retriable=False)
        bus = _bus(channel)

        await MessageEffects(bus).edit_placeholder("test", "chat-1", "ph-1", _reply("Report ready", media=(doc,)))

        (full_reply,) = _published(bus)
        assert (full_reply.content, full_reply.media) == ("Report ready", (doc,))
        assert Path(doc.path).exists()  # the bus delivers it and removes it afterwards
        Path(doc.path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_attachments_the_channel_cannot_carry_become_a_note_and_release_their_files(self) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = _channel(media=False)
        bus = _bus(channel)

        await MessageEffects(bus).edit_placeholder("test", "chat-1", "ph-1", _reply("Report ready", media=(doc,)))

        assert "report.pdf" in _edited(channel).content
        bus.publish_outbound.assert_not_awaited()
        assert not Path(doc.path).exists()

    @pytest.mark.asyncio
    async def test_the_edit_goes_through_the_outbound_risk_gate(self) -> None:
        channel = _channel()
        bus = _bus(channel)

        def _block(msg: OutboundMessage) -> OutboundMessage:
            return OutboundMessage(channel=msg.channel, recipient_id=msg.recipient_id, content="[blocked]", user_id="u1")

        with patch("app.channels.core.outbound_prepare.apply_outbound_risk_gate", side_effect=_block):
            await MessageEffects(bus).edit_placeholder("test", "chat-1", "ph-1", _reply("secret"))

        assert _edited(channel).content == "[blocked]"
