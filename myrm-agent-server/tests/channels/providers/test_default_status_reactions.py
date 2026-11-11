"""What each reaction-capable channel shows for the router's default status reactions.

A platform with its own reaction vocabulary shows the nearest accepted glyph (or nothing when it has
none), never a rejected glyph and never a success glyph or a thumbs-down for a failure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.registry import get_channel_class
from app.channels.routing.reactions import ReactionFunnel, StatusReaction, TurnOutcome
from app.channels.routing.router_models import ReactionPolicy
from tests.channels.channel_class_testkit import channel_class_or_skip, channels_missing_their_sdk

EYES = "\U0001f440"
CHECK = "\u2705"
CROSS = "\u274c"
THUMBS_UP = "\U0001f44d"
CRYING = "\U0001f622"

# (processing, success, failure); None = the platform has no faithful glyph, so nothing is shown.
EXPECTED: dict[str, tuple[str | None, str, str | None]] = {
    "telegram": (EYES, THUMBS_UP, CRYING),
    "teams": (EYES, CHECK, CROSS),
    "imessage": (None, THUMBS_UP, None),
    "feishu": (EYES, CHECK, CROSS),
    "slack": (EYES, CHECK, CROSS),
    "mattermost": (EYES, CHECK, CROSS),
    "discord": (EYES, CHECK, CROSS),
    "matrix": (EYES, CHECK, CROSS),
    "signal": (EYES, CHECK, CROSS),
    "whatsapp": (EYES, CHECK, CROSS),
    "dingtalk": (EYES, CHECK, CROSS),
}


async def _shown(channel: str, *, state: str) -> str | None:
    ch = MagicMock()
    ch.capabilities = channel_class_or_skip(channel).capabilities
    ch.react_to_message = AsyncMock()
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=ch)
    status = StatusReaction(ReactionFunnel(bus), ReactionPolicy(), channel, "chat", "m1")
    if state == "processing":
        status.received()
        await status.marked()
    else:
        await status.finish(TurnOutcome.COMPLETED if state == "success" else TurnOutcome.FAILED)
    return ch.react_to_message.await_args.args[2] if ch.react_to_message.await_args else None


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", sorted(EXPECTED))
async def test_default_status_reactions_per_channel(channel: str) -> None:
    processing, success, failure = EXPECTED[channel]
    assert await _shown(channel, state="processing") == processing
    assert await _shown(channel, state="success") == success
    assert await _shown(channel, state="failure") == failure


def test_every_reaction_capable_channel_is_covered() -> None:
    from app.channels.providers.registry import CHANNEL_META

    # A channel whose optional SDK is not installed cannot report its capabilities, so the table's entry for it is not compared.
    unavailable = channels_missing_their_sdk()
    capable = {
        name
        for name in CHANNEL_META
        if name not in unavailable
        and not isinstance(get_channel_class(name).capabilities, property)
        and get_channel_class(name).capabilities.reactions
    }
    assert capable == set(EXPECTED) - unavailable
