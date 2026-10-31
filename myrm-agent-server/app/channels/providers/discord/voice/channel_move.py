"""Moving a live voice session to another channel, with the outcome checked.

[INPUT]
- app.channels.providers.discord.voice.follow::VoiceTarget (POS: a voice or stage channel a session can sit in)

[OUTPUT]
- is_in_channel: whether a VoiceClient is connected and sits in a channel
- move_to_channel: moves a connected VoiceClient to a channel and reports whether it is connected there afterwards

[POS]
The move half of a join over a live session. discord.py's ``VoiceClient.move_to`` documents a ``TimeoutError`` for a move
that did not complete, but its connection state logs the timeout, rolls back and returns normally; where the client is
afterwards is the only reliable outcome, so a move counts only when the client is connected in the target channel.
"""

from __future__ import annotations

import logging

import discord

from app.channels.providers.discord.voice.follow import (
    VoiceTarget,
)

logger = logging.getLogger(__name__)


def is_in_channel(voice_client: discord.VoiceClient, channel: VoiceTarget) -> bool:
    """Whether the client is connected and sits in ``channel``."""
    return voice_client.is_connected() and bool(voice_client.channel) and voice_client.channel.id == channel.id


async def move_to_channel(voice_client: discord.VoiceClient, channel: VoiceTarget) -> bool:
    """Move a connected client to ``channel``; False, with the reason logged, unless it ends up connected there."""
    try:
        await voice_client.move_to(channel)
    except Exception as e:
        logger.error("Failed to move to voice channel %s: %s", channel.id, e)
        return False
    if not is_in_channel(voice_client, channel):
        logger.error("Move to voice channel %s did not complete", channel.id)
        return False
    return True
