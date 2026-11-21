"""Buttons and menus on Discord: its outbound sends text and files only, so they reach the user as text."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.core.outbound_prepare import prepare_outbound
from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig
from app.channels.types import ActionButton, OutboundMessage, SelectMenu, SelectOption

_SHARE_URL = "https://example.test/s/tok123"

_LINK = ActionButton(label="Open", action_id="artifact:share:art-1", url=_SHARE_URL)
_CALLBACK = ActionButton(label="Approve", action_id="approval:approve:req-1")
_MENU = SelectMenu(
    action_id="pick:model",
    placeholder="Pick one",
    options=(SelectOption(label="Fast", value="fast"), SelectOption(label="Deep", value="deep")),
)


async def _deliver(component: ActionButton | SelectMenu) -> MagicMock:
    """Prepare a reply carrying ``component`` for Discord, send it, and return the Discord channel it went to."""
    reply = OutboundMessage(channel="discord", recipient_id="1", content="Report ready", user_id="u1", components=((component,),))
    prepared = prepare_outbound(reply, DiscordChannel.capabilities, channel_name="discord")
    target = MagicMock(spec=discord.TextChannel)
    target.send = AsyncMock(return_value=MagicMock(id=42))
    channel = DiscordChannel(DiscordChannelConfig(bot_token="test_token"))
    channel._resolve_channel = AsyncMock(return_value=target)

    await channel.send(prepared)

    return target


def test_the_adapter_declares_no_native_components() -> None:
    capabilities = DiscordChannel.capabilities

    assert (capabilities.buttons, capabilities.select_menus) == (False, False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("component", "line"),
    [
        (_LINK, f"• Open → {_SHARE_URL}"),
        (_CALLBACK, "• Approve → /approve:req-1"),
        (_MENU, "• Pick one: Fast, Deep"),
    ],
)
async def test_a_component_reaches_discord_as_a_text_line(component: ActionButton | SelectMenu, line: str) -> None:
    target = await _deliver(component)

    target.send.assert_awaited_once()
    sent = target.send.call_args.kwargs
    assert sent["content"] == f"Report ready\n\n{line}"
    assert "view" not in sent
