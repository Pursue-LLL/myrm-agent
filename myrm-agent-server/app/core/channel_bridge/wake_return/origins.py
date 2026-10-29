"""Where each of the owner's IM chats lives, so what a wake turn says can go back to it.

[INPUT]
- app.channels.types::InboundMessage (POS: the message of an IM turn; names its channel, chat, thread and sender)

[OUTPUT]
- WakeOrigins: a bounded memory of one origin message per chat
- get_wake_origins: the process-wide instance

[POS]
Written by the IM turns of the owner's direct chats once the chat is known (a wake turn runs with the owner's whole
memory, so groups and guests never get an entry), read when a wake turn of that chat has something to say. The origin
is kept as the message itself because the chat row only stores a session key, which is lowercased and stripped of
characters a channel's peer id may need. The memory is bounded and lost on restart; a wake turn after a restart
answers in the app only.
"""

from __future__ import annotations

import dataclasses
from collections import OrderedDict

from app.channels.types import InboundMessage

_MAX_ORIGINS = 256
# Enough of the member's text for a held draft to show what it answers (a draft keeps no more than this).
_MAX_CONTENT_CHARS = 500
# Chats that are not a conversation to come back to: the app's own chats and a live phone call.
_UNRETURNABLE_CHANNELS = frozenset({"web", "chat", "voice"})


class WakeOrigins:
    """The latest message of each remembered chat, the one written longest ago first out."""

    def __init__(self, capacity: int = _MAX_ORIGINS) -> None:
        self._capacity = capacity
        self._by_chat: OrderedDict[str, InboundMessage] = OrderedDict()

    def remember(self, chat_id: str, msg: InboundMessage) -> None:
        """Note ``msg`` as where ``chat_id`` is being talked in; a chat in the app itself has no outside to return to."""
        if msg.channel in _UNRETURNABLE_CHANNELS:
            return
        self._by_chat[chat_id] = _routing_copy(msg)
        self._by_chat.move_to_end(chat_id)
        while len(self._by_chat) > self._capacity:
            self._by_chat.popitem(last=False)

    def get(self, chat_id: str) -> InboundMessage | None:
        return self._by_chat.get(chat_id)


def _routing_copy(msg: InboundMessage) -> InboundMessage:
    """``msg`` without what a reply never needs: attachments, quoted context and anything but plain-text metadata."""
    return dataclasses.replace(
        msg,
        content=msg.content[:_MAX_CONTENT_CHARS],
        media=(),
        context_messages=(),
        reply_to=None,
        resume_value=None,
        metadata={key: value for key, value in msg.metadata.items() if isinstance(value, str)},
    )


_origins = WakeOrigins()


def get_wake_origins() -> WakeOrigins:
    """The process-wide origins the IM turns write and the returner reads."""
    return _origins
