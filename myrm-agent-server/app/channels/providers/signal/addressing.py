"""Signal addressing — how a chat and the author of a message are named on the signal-cli-rest-api wire.

[INPUT]
- (none)

[OUTPUT]
- is_group_id / wire_recipient: the recipient form signal-cli-rest-api accepts for a chat
- MessageAuthors: bounded memory of who wrote each group message

[POS]
signal-cli reports a group by its bare id (base64 of 32 bytes), while the REST wrapper accepts a group only as
``group.`` + the base64 of that text and reads any other string as a username. A reaction also names the author
of the message it targets; only group chats leave that unknown, because in a direct chat the author is the chat.
"""

from __future__ import annotations

import base64
from collections import OrderedDict

_GROUP_PREFIX = "group."
_GROUP_ID_BYTES = 32
_MAX_TRACKED_MESSAGES = 1024


def is_group_id(chat_id: str) -> bool:
    """True for the bare group id signal-cli reports: base64 of exactly 32 bytes, which no number or UUID decodes to."""
    try:
        return len(base64.b64decode(chat_id, validate=True)) == _GROUP_ID_BYTES
    except ValueError:
        return False


def wire_recipient(chat_id: str) -> str:
    """The recipient string for ``chat_id``: groups get the ``group.`` form, numbers and UUIDs go as they are."""
    if not is_group_id(chat_id):
        return chat_id
    return _GROUP_PREFIX + base64.b64encode(chat_id.encode()).decode()


class MessageAuthors:
    """Author of each recent group message, oldest entries evicted first."""

    def __init__(self, max_entries: int = _MAX_TRACKED_MESSAGES) -> None:
        self._max_entries = max_entries
        self._authors: OrderedDict[tuple[str, str], str] = OrderedDict()

    def note(self, chat_id: str, message_id: str, author: str) -> None:
        key = (chat_id, message_id)
        self._authors[key] = author
        self._authors.move_to_end(key)
        while len(self._authors) > self._max_entries:
            self._authors.popitem(last=False)

    def author_of(self, chat_id: str, message_id: str) -> str | None:
        """The message's author, or ``None`` for a group message that was never seen."""
        if not is_group_id(chat_id):
            return chat_id
        return self._authors.get((chat_id, message_id))
