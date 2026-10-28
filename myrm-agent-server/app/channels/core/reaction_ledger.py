"""Bounded memory of the reaction a channel put on each message.

[INPUT]
- (none)

[OUTPUT]
- ReactionLedger: remember / take the handle needed to undo a reaction added to a message

[POS]
The router clears a status reaction by calling ``react_to_message`` with an empty emoji, but most
platforms remove a reaction by naming it (Slack, Discord, Mattermost) or by an id the add call
returned (Feishu). A channel keeps one ledger so the empty emoji removes exactly what it added,
and makes no call when it added nothing. Entries are bounded because a completion reaction is
never removed.
"""

from __future__ import annotations

from collections import OrderedDict

_DEFAULT_MAX_ENTRIES = 1024


class ReactionLedger:
    """Latest reaction handle per ``(chat_id, message_id)``, oldest entries evicted first."""

    def __init__(self, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._handles: OrderedDict[tuple[str, str], str] = OrderedDict()

    def remember(self, chat_id: str, message_id: str, handle: str) -> None:
        """Record the handle that undoes the reaction just added to the message."""
        key = (chat_id, message_id)
        self._handles[key] = handle
        self._handles.move_to_end(key)
        while len(self._handles) > self._max_entries:
            self._handles.popitem(last=False)

    def take(self, chat_id: str, message_id: str) -> str | None:
        """Pop the handle for the message, or ``None`` when no reaction was recorded."""
        return self._handles.pop((chat_id, message_id), None)
