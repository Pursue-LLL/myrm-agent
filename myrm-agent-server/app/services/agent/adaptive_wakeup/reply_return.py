"""Hand what a wake turn said to whoever carries it back to where the conversation started.

[INPUT]
- (none: the carrier is registered at startup by whoever owns the outside channel)

[OUTPUT]
- WakeReplyReturner: the one method a carrier implements
- set_wake_reply_returner: register (or clear) the carrier
- return_wake_reply: give a finished wake turn's reply to the carrier; never raises

[POS]
Port of a wake turn. The turn streams into the chat it belongs to; a chat that was started from an IM channel also
has someone waiting there, and only the channel bridge knows how to reach them. A reply that cannot be returned
stays in the chat, where the web UI shows it.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class WakeReplyReturner(Protocol):
    """Carries a wake turn's reply to the place outside the app where its chat was started."""

    async def return_reply(self, chat_id: str, reply: str) -> None: ...


_returner: WakeReplyReturner | None = None


def set_wake_reply_returner(returner: WakeReplyReturner | None) -> None:
    """Register the carrier; ``None`` removes it."""
    global _returner  # noqa: PLW0603
    _returner = returner


async def return_wake_reply(chat_id: str, reply: str) -> None:
    """Give ``reply`` of a finished wake turn of ``chat_id`` to the carrier, if there is one.

    A carrier that fails is logged and swallowed: the reply is already saved in the chat, and the wake turn is over.
    """
    if _returner is None:
        return
    try:
        await _returner.return_reply(chat_id, reply)
    except Exception:
        logger.warning("The reply of a wake turn could not be returned: session=%s", chat_id, exc_info=True)
