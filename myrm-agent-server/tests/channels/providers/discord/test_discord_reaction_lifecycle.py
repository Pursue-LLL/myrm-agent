"""Discord removes the bot's own reaction through ``Message.remove_reaction``; failures reach the caller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig

EYES = "\U0001f440"


def _channel() -> tuple[DiscordChannel, MagicMock, MagicMock]:
    ch = DiscordChannel(DiscordChannelConfig(bot_token="tok", enable_gateway=True, allowed_users=["1"], allowed_guilds=["2"]))
    ch._client = MagicMock()
    ch._client.user = MagicMock(name="bot")
    message = MagicMock()
    message.add_reaction = AsyncMock()
    message.remove_reaction = AsyncMock()
    messageable = MagicMock()
    messageable.fetch_message = AsyncMock(return_value=message)
    ch._resolve_channel = AsyncMock(return_value=messageable)  # type: ignore[method-assign]
    return ch, message, messageable


@pytest.mark.asyncio
async def test_an_empty_emoji_removes_the_reaction_that_was_added() -> None:
    ch, message, messageable = _channel()

    await ch.react_to_message("123", "456", EYES)
    await ch.react_to_message("123", "456", "")

    message.remove_reaction.assert_awaited_once_with(EYES, ch._client.user)
    messageable.fetch_message.assert_awaited_with(456)


@pytest.mark.asyncio
async def test_an_empty_emoji_touches_nothing_when_no_reaction_was_added() -> None:
    ch, message, _ = _channel()

    await ch.react_to_message("123", "456", "")

    message.remove_reaction.assert_not_awaited()
    ch._resolve_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_reaction_is_removed_only_once() -> None:
    ch, message, _ = _channel()

    await ch.react_to_message("123", "456", EYES)
    await ch.react_to_message("123", "456", "")
    await ch.react_to_message("123", "456", "")

    message.remove_reaction.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failed_add_raises_and_is_not_remembered() -> None:
    ch, message, _ = _channel()
    message.add_reaction.side_effect = RuntimeError("Missing Permissions")

    with pytest.raises(RuntimeError, match="Missing Permissions"):
        await ch.react_to_message("123", "456", EYES)
    await ch.react_to_message("123", "456", "")

    message.remove_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_without_a_bot_user_nothing_can_be_removed() -> None:
    ch, message, _ = _channel()
    await ch.react_to_message("123", "456", EYES)
    ch._client.user = None

    await ch.react_to_message("123", "456", "")

    message.remove_reaction.assert_not_awaited()
