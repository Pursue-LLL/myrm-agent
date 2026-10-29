"""Unit tests for the mention policy of the Discord gateway client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("discord")
from discord.http import handle_message_parameters

from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig


@pytest.mark.asyncio
async def test_gateway_client_cannot_notify_everyone_or_roles() -> None:
    """Guests steer the agent's text, so no message the client sends may notify a whole server or a role."""
    channel = DiscordChannel(DiscordChannelConfig(bot_token="test_token", enable_gateway=True))
    with patch("discord.Client") as client_cls:
        client_cls.return_value.start = AsyncMock()
        await channel.start()

    client_default = client_cls.call_args.kwargs["allowed_mentions"]

    # What discord.py puts on the wire for a send or an edit that sets no mention policy of its own.
    with handle_message_parameters(content="@everyone <@&1> <@2>", previous_allowed_mentions=client_default) as params:
        assert params.payload is not None
        wire = params.payload["allowed_mentions"]

    # A reply still notifies the person it answers.
    assert wire == {"parse": ["users"], "replied_user": True}
