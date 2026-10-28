"""The one place a reaction leaves the router: best-effort, in the vocabulary the platform accepts.

[INPUT]
- channels.core.bus::MessageBus (POS: async message bus that resolves a channel by name)

[OUTPUT]
- ReactionFunnel: ``react`` sets or takes off a reaction without ever failing the caller, ``accepted`` picks the first glyph a platform takes

[POS]
Every reaction the router makes goes through here (``StatusReaction`` and the TTL janitor). A reaction decorates a
turn, so a failure never reaches it; a failure that keeps repeating (a missing permission, an unsupported glyph) is
still made visible, once per window per channel and error type, instead of looking like a bot without status marks.
"""

from __future__ import annotations

import logging
import time

from app.channels.core.bus import MessageBus

logger = logging.getLogger(__name__)

_WARN_INTERVAL = 600.0


class ReactionFunnel:
    """Sends reactions through the bus' channels; reports a failure that keeps happening once per window."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._warned_at: dict[tuple[str, str], float] = {}

    async def react(self, channel: str, chat_id: str, message_id: object, emoji: str) -> None:
        """Best-effort message reaction; an empty ``emoji`` takes off what this channel added."""
        if not isinstance(message_id, str) or not message_id:
            return
        ch = self._bus.get_channel(channel)
        if not ch or not ch.capabilities.reactions:
            return
        try:
            await ch.react_to_message(chat_id, message_id, emoji)
        except Exception as exc:
            self._report_failure(channel, exc)

    def accepted(self, channel: str, preferred: str, fallbacks: tuple[str, ...]) -> str:
        """First glyph of ``preferred`` then ``fallbacks`` the platform accepts; ``""`` skips the reaction.

        An empty ``preferred`` means the status reaction is switched off, so no fallback applies.
        """
        ch = self._bus.get_channel(channel)
        if not preferred or not ch:
            return ""
        return next((g for g in (preferred, *fallbacks) if ch.capabilities.accepts_reaction(g)), "")

    def _report_failure(self, channel: str, exc: Exception) -> None:
        key = (channel, type(exc).__name__)
        now = time.monotonic()
        last_warned = self._warned_at.get(key)
        if last_warned is not None and now - last_warned < _WARN_INTERVAL:
            logger.debug("reaction failed on %s: %s", channel, exc)
            return
        self._warned_at[key] = now
        logger.warning("Status reaction failed on %s (%s): %s", channel, key[1], str(exc)[:300])
