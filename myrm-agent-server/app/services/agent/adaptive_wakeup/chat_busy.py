"""Ask whoever runs turns outside the app's own gateway whether one of them holds a chat.

[INPUT]
- (none: the probe is registered at startup by whoever owns the outside channel)

[OUTPUT]
- ChatBusyProbe: the one method a probe implements
- set_chat_busy_probe: register (or clear) the probe
- is_chat_busy: whether the probe says a turn holds the chat; never raises

[POS]
Port of a wake turn. A turn that came in from an IM channel is run by the channel router, not by the agent gateway,
so the gateway cannot tell that the member is mid-conversation; the wake turn asks this port before it takes the chat.
The question is synchronous: the scheduler takes the chat in the step that follows the answer, and an await in between
would let a turn slip in.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class ChatBusyProbe(Protocol):
    """Knows whether a turn that does not run through the agent gateway holds a chat."""

    def is_busy(self, chat_id: str) -> bool: ...


_probe: ChatBusyProbe | None = None


def set_chat_busy_probe(probe: ChatBusyProbe | None) -> None:
    """Register the probe; ``None`` removes it."""
    global _probe  # noqa: PLW0603
    _probe = probe


def is_chat_busy(chat_id: str) -> bool:
    """Whether a turn outside the agent gateway holds ``chat_id``; False without a probe.

    A probe that fails is logged and counted as not busy: waiting on a broken probe would lose the wake turn.
    """
    if _probe is None:
        return False
    try:
        return _probe.is_busy(chat_id)
    except Exception:
        logger.warning("The busy probe failed, treating the chat as free: session=%s", chat_id, exc_info=True)
        return False
