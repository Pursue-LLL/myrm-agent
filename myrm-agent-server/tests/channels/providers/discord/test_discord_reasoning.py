"""A Discord reply shows the agent's reasoning once, as a Markdown quote, and none when the reply hides it."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig
from app.channels.rendering.renderer import mark_rendered, render
from app.channels.types import OutboundMessage

_REASONING = "weighing two options"


def _reply(**overrides: object) -> OutboundMessage:
    fields: dict[str, object] = {
        "channel": "discord",
        "recipient_id": "123",
        "content": "The answer",
        "user_id": "u1",
        "reasoning": _REASONING,
    }
    fields.update(overrides)
    return OutboundMessage(**fields)  # type: ignore[arg-type]


def _rendered_by_the_router(msg: OutboundMessage) -> OutboundMessage:
    """What the router hands the channel: the reply rendered once with the channel's style."""
    return mark_rendered(msg, render(msg, DiscordChannel.render_style)[0])


async def _edit_placeholder_with(msg: OutboundMessage) -> discord.Embed:
    channel = DiscordChannel(DiscordChannelConfig(bot_token="test_token"))
    target = MagicMock()
    target.edit = AsyncMock()
    messageable = MagicMock()
    messageable.fetch_message = AsyncMock(return_value=target)
    channel._resolve_channel = AsyncMock(return_value=messageable)

    await channel.edit_placeholder_message("123", "456", msg)

    return target.edit.call_args.kwargs["embed"]


def test_the_reasoning_is_a_markdown_quote_not_html_tags() -> None:
    text = "".join(render(_reply(), DiscordChannel.render_style))

    assert f"> {_REASONING}" in text
    assert "<blockquote" not in text


@pytest.mark.asyncio
async def test_the_placeholder_edit_carries_the_reasoning_once() -> None:
    embed = await _edit_placeholder_with(_rendered_by_the_router(_reply()))

    assert embed.footer.text is None
    assert (embed.description or "").count(_REASONING) == 1


@pytest.mark.asyncio
async def test_a_reply_that_hides_its_reasoning_shows_none_in_the_placeholder() -> None:
    embed = await _edit_placeholder_with(_rendered_by_the_router(_reply(metadata={"reasoning_display_mode": "off"})))

    assert embed.footer.text is None
    assert _REASONING not in (embed.description or "")
    assert embed.description == "The answer"
