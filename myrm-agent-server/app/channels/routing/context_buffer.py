"""Group context buffer — accumulates non-trigger messages for context injection.

Non-trigger group messages are stored per chat_id. When a trigger message
arrives, the buffer is drained and injected into InboundMessage.context_messages,
giving the Agent conversational context from the group chat.

[INPUT]
- channels.types::ContextEntry (POS: Non-trigger message metadata with sender/content/timestamp.)

[OUTPUT]
- GroupContextBuffer: per-group ring buffer with time-based expiry

[POS]
Pure in-memory buffer, no I/O, no lifecycle management.
Drains expired messages by time filter and clears the group buffer.
"""

from __future__ import annotations

import time
from collections import deque

from app.channels.types import ContextEntry

_DEFAULT_MAX_PER_GROUP = 20
_DEFAULT_MAX_AGE_SECONDS = 3600.0


class GroupContextBuffer:
    """Per-group ring buffer that accumulates non-trigger messages.

    Thread-safety: not required — all access is from the single-threaded
    asyncio event loop via AgentRouter.
    """

    __slots__ = ("_max_age", "_max_per_group", "_store")

    def __init__(
        self,
        max_per_group: int = _DEFAULT_MAX_PER_GROUP,
        max_age_seconds: float = _DEFAULT_MAX_AGE_SECONDS,
    ) -> None:
        self._store: dict[str, deque[ContextEntry]] = {}
        self._max_per_group = max_per_group
        self._max_age = max_age_seconds

    def append(self, chat_id: str, entry: ContextEntry) -> None:
        """Store a non-trigger message for later context injection."""
        buf = self._store.get(chat_id)
        if buf is None:
            buf = deque(maxlen=self._max_per_group)
            self._store[chat_id] = buf
        buf.append(entry)

    def drain(self, chat_id: str) -> tuple[ContextEntry, ...]:
        """Take all accumulated messages for a group, filtering expired ones.

        The buffer for this chat_id is cleared after draining.
        """
        buf = self._store.pop(chat_id, None)
        if not buf:
            return ()

        cutoff = time.monotonic() - self._max_age
        return tuple(e for e in buf if e.timestamp >= cutoff)

    def clear(self, chat_id: str) -> None:
        """Explicitly clear a group's buffer (e.g. when group is disabled)."""
        self._store.pop(chat_id, None)

    def clear_all(self) -> None:
        """Clear all buffers (e.g. on shutdown)."""
        self._store.clear()
