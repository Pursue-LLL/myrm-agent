"""Per-conversation loop guard for bot-authored inbound triggers.

The bot-sender gate (policy_resolver_support) only admits bot messages that
explicitly address this agent, which keeps bot-to-bot automation possible.
Two automated agents replying to each other can still ping-pong forever, so
this guard caps the exchange: it counts admitted bot triggers per
conversation and drops further ones for `cooldown_seconds` once `max_events`
land inside `window_seconds`. Human messages are never counted and never
dropped.

Design:
- Sliding window counter per conversation ("{channel}:{chat_id}")
- O(1) admit; periodic sweep keeps memory bounded
- Pure in-memory, asyncio-loop confined (no locking; same model as
  SessionRateLimiter)
- Built-in safety default: always on, no config surface

Usage:
    guard = BotLoopGuard()
    allowed, state = guard.admit(f"{msg.channel}:{msg.chat_id}")
    if not allowed:
        logger.warning("BotLoopGuard %s in %s", state, key)

[INPUT]
- (none)

[OUTPUT]
- BotLoopGuard: Per-conversation sliding-window guard for bot-authored triggers.

[POS]
Bot-to-bot reply loop protection: caps admitted bot triggers per conversation.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

# Safety defaults mirroring the reference implementation (Hermes bot_loop_guard):
# 20 bot-triggered turns within 5 minutes trip a 10-minute cooldown.
DEFAULT_MAX_EVENTS = 20
DEFAULT_WINDOW_SECONDS = 300.0
DEFAULT_COOLDOWN_SECONDS = 600.0


class BotLoopGuard:
    """Sliding-window budget for bot-authored triggers with a tripped cooldown.

    Args:
        max_events: Bot triggers allowed per conversation within the window.
        window_seconds: Sliding window length for counting bot triggers.
        cooldown_seconds: How long further bot triggers are dropped after tripping.
        clock: Monotonic time source (injectable for tests).
    """

    def __init__(
        self,
        max_events: int = DEFAULT_MAX_EVENTS,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_events = max_events
        self._window_seconds = window_seconds
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._cooldown_until: dict[str, float] = {}
        self._last_sweep = 0.0

    @property
    def tracked_conversations(self) -> int:
        """Number of conversations currently holding state (observability/tests)."""
        return len(self._events) + len(self._cooldown_until)

    def admit(self, conversation: str) -> tuple[bool, str]:
        """Count one admitted bot trigger for the conversation.

        Returns:
            (allowed, state) where state is "ok", "tripped" (this message
            started the cooldown) or "cooldown" (dropped while cooling down).
        """
        now = self._clock()
        self._sweep(now)

        if self._cooldown_until.get(conversation, 0.0) > now:
            return False, "cooldown"

        events = self._events.setdefault(conversation, deque())
        cutoff = now - self._window_seconds
        while events and events[0] <= cutoff:
            events.popleft()

        if len(events) >= self._max_events:
            self._cooldown_until[conversation] = now + self._cooldown_seconds
            events.clear()
            return False, "tripped"

        events.append(now)
        return True, "ok"

    def reset(self, conversation: str) -> None:
        """Clear window and cooldown for one conversation (tests/admin)."""
        self._events.pop(conversation, None)
        self._cooldown_until.pop(conversation, None)

    def _sweep(self, now: float) -> None:
        """Drop idle conversations at most once per window so memory stays bounded."""
        if now - self._last_sweep < self._window_seconds:
            return
        self._last_sweep = now
        idle_cutoff = now - self._window_seconds
        for key in [k for k, dq in self._events.items() if not dq or dq[-1] <= idle_cutoff]:
            del self._events[key]
        for key in [k for k, until in self._cooldown_until.items() if until <= now]:
            del self._cooldown_until[key]