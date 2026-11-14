"""What the Discord channel does with a placeholder, a delete, a reaction or a typing hint Discord cannot take."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig
from app.channels.types import OutboundMessage


def _channel(messageable: object | None) -> DiscordChannel:
    """A channel that resolves every chat id to ``messageable`` (None: Discord cannot reach it)."""
    channel = DiscordChannel(DiscordChannelConfig(bot_token="test_token"))
    channel._resolve_channel = AsyncMock(return_value=messageable)
    return channel


def _text_channel() -> MagicMock:
    return MagicMock(spec=discord.TextChannel)


def _refusal(status: int = 403) -> discord.HTTPException:
    return discord.HTTPException(MagicMock(status=status, reason="refused"), "refused")


class TestSendPlaceholder:
    @pytest.mark.asyncio
    async def test_the_id_of_the_message_sent_is_the_placeholder(self) -> None:
        target = _text_channel()
        target.send = AsyncMock(return_value=MagicMock(id=555))

        assert await _channel(target).send_placeholder("1", "Thinking...") == "555"

        target.send.assert_awaited_once_with(content="Thinking...")

    @pytest.mark.asyncio
    async def test_an_unreachable_channel_has_no_placeholder(self) -> None:
        assert await _channel(None).send_placeholder("1", "Thinking...") is None

    @pytest.mark.asyncio
    async def test_a_refused_message_has_no_placeholder_and_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        target = _text_channel()
        target.send = AsyncMock(side_effect=_refusal())

        with caplog.at_level(logging.ERROR):
            assert await _channel(target).send_placeholder("1", "Thinking...") is None

        assert "Failed to send placeholder" in caplog.text


class TestDeleteMessage:
    @pytest.mark.asyncio
    async def test_an_unreachable_channel_is_left_alone(self) -> None:
        await _channel(None).delete_message("1", "2")

    @pytest.mark.asyncio
    async def test_a_message_that_cannot_be_deleted_never_fails_the_caller(self, caplog: pytest.LogCaptureFixture) -> None:
        target = _text_channel()
        target.fetch_message = AsyncMock(side_effect=_refusal(404))

        with caplog.at_level(logging.ERROR):
            await _channel(target).delete_message("1", "2")

        assert "Failed to delete message 2" in caplog.text


class TestReactions:
    @pytest.mark.asyncio
    async def test_a_reaction_to_an_unreachable_channel_is_dropped(self) -> None:
        await _channel(None).react_to_message("1", "2", "👍")

    @pytest.mark.asyncio
    async def test_an_empty_emoji_takes_back_the_reaction_this_channel_added(self) -> None:
        message = MagicMock(add_reaction=AsyncMock(), remove_reaction=AsyncMock())
        target = _text_channel()
        target.fetch_message = AsyncMock(return_value=message)
        channel = _channel(target)
        channel._client = MagicMock()

        await channel.react_to_message("1", "2", "👍")
        await channel.react_to_message("1", "2", "")

        message.remove_reaction.assert_awaited_once_with("👍", channel._client.user)

    @pytest.mark.asyncio
    async def test_a_reaction_cannot_be_taken_back_once_the_channel_is_gone(self) -> None:
        message = MagicMock(add_reaction=AsyncMock(), remove_reaction=AsyncMock())
        target = _text_channel()
        target.fetch_message = AsyncMock(return_value=message)
        channel = _channel(target)
        channel._client = MagicMock()
        await channel.react_to_message("1", "2", "👍")

        channel._resolve_channel = AsyncMock(return_value=None)
        await channel.react_to_message("1", "2", "")

        message.remove_reaction.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_reaction_this_channel_never_added_is_not_taken_back(self) -> None:
        channel = _channel(_text_channel())
        channel._client = MagicMock()

        await channel.react_to_message("1", "2", "")

        channel._resolve_channel.assert_not_awaited()


class TestTypingHint:
    @pytest.mark.asyncio
    async def test_an_unreachable_channel_gets_no_hint(self) -> None:
        await _channel(None).start_typing("1")

    @pytest.mark.asyncio
    async def test_a_refused_hint_is_only_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        target = _text_channel()
        target.typing = AsyncMock(side_effect=_refusal())

        with caplog.at_level(logging.ERROR):
            await _channel(target).start_typing("1")

        assert "Failed to start typing in 1" in caplog.text


class TestFilesWithoutText:
    @pytest.mark.asyncio
    async def test_files_without_text_go_out_alone_and_the_last_message_id_is_returned(self) -> None:
        target = _text_channel()
        target.send = AsyncMock(return_value=MagicMock(id=9))
        attachment = MagicMock(spec=discord.File)
        message = OutboundMessage(channel="discord", recipient_id="1", content="", user_id="u1")

        assert await _channel(target)._send_chunks(target, message, [attachment]) == "9"

        target.send.assert_awaited_once_with(files=[attachment])

    @pytest.mark.asyncio
    async def test_a_message_of_nothing_sends_nothing(self) -> None:
        target = _text_channel()
        target.send = AsyncMock()
        message = OutboundMessage(channel="discord", recipient_id="1", content="", user_id="u1")

        assert await _channel(target)._send_chunks(target, message, []) is None

        target.send.assert_not_awaited()


class TestResolveChannel:
    @pytest.mark.asyncio
    async def test_a_chat_id_that_is_not_a_messageable_channel_is_unreachable(self) -> None:
        channel = DiscordChannel(DiscordChannelConfig(bot_token="test_token"))
        channel._client = MagicMock()
        channel._client.get_channel = MagicMock(return_value=None)
        channel._client.fetch_channel = AsyncMock(return_value=MagicMock(spec=discord.CategoryChannel))

        assert await channel._resolve_channel("1") is None
