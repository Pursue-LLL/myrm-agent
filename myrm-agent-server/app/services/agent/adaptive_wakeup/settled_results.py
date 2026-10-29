"""Which settlements a chat's next wake turn answers, and which of their results the agent already read.

[INPUT]
- None (stdlib only)

[OUTPUT]
- SettledResults: per-chat ledger; ``queue`` a settlement, ``mark_read`` results the agent read itself,
  ``take_all_read`` when the wake turn takes the chat

[POS]
A wake turn exists to hand the agent results it has not seen. A background task can settle while the agent's own turn
is still running; if that turn lists its subagents it reads the result there, and the wake turn queued behind it would
answer the same result a second time. The wake turn asks this ledger just before it would start.
"""

from __future__ import annotations

from collections.abc import Iterable

# The harness keeps at most this many settled children around, so a chat never has more to remember.
_MAX_READ_PER_CHAT = 200


class SettledResults:
    """Settlements waiting for a wake turn, and the results the agent has read, by chat id."""

    __slots__ = ("_queued", "_read")

    def __init__(self) -> None:
        self._queued: dict[str, set[str]] = {}
        # Insertion-ordered so the oldest mark goes first when a chat reads more than it can keep.
        self._read: dict[str, dict[str, None]] = {}

    def queue(self, chat_id: str, source_id: str) -> None:
        """A settlement the chat's next wake turn will answer."""
        self._queued.setdefault(chat_id, set()).add(source_id)

    def mark_read(self, chat_id: str, source_ids: Iterable[str]) -> None:
        """The agent received these settled results in a tool call of its own."""
        read = self._read.setdefault(chat_id, {})
        for source_id in source_ids:
            read.pop(source_id, None)
            read[source_id] = None
        while len(read) > _MAX_READ_PER_CHAT:
            del read[next(iter(read))]

    def take_all_read(self, chat_id: str) -> bool:
        """The wake turn takes the chat: whether the agent already read every result it would answer.

        The queue and the marks of those results are cleared; a settlement that lands later belongs to the next wake turn.
        """
        queued = self._queued.pop(chat_id, set())
        read = self._read.get(chat_id, {})
        all_read = bool(queued) and queued.issubset(read)
        for source_id in queued:
            read.pop(source_id, None)
        if not read:
            self._read.pop(chat_id, None)
        return all_read

    def forget(self, chat_id: str) -> None:
        """Drop everything held for a chat that is gone."""
        self._queued.pop(chat_id, None)
        self._read.pop(chat_id, None)
