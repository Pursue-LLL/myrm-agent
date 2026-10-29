"""Group context buffer — accumulates non-trigger messages for context injection.

Non-trigger group messages are stored per chat_id. When a trigger message
arrives, the buffer is drained and injected into InboundMessage.context_messages,
giving the Agent conversational context from the group chat.

[INPUT]
- channels.types::ContextEntry (POS: Non-trigger message metadata with sender/content/timestamp.)
- channels.routing.channel_data_plane::ChannelDataPlaneService (POS: persisted inbound/outbound channel history)

[OUTPUT]
- GroupContextBuffer: per-group ring buffer with time-based expiry
- GroupContextBuffer.drain_async: persisted context first, in-memory entries as the fallback

[POS]
Group chat context accumulation. append() records non-trigger chatter in memory; drain() takes
it back for injection into the next trigger turn, and drain_async() prefers the persisted data
plane, keeping the in-memory entries whenever that plane has nothing to return. Both paths hand
out a message once and only while it is younger than the expiry: the persisted path remembers when
a chat was last taken instead of deleting ledger rows.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timedelta, timezone

from app.channels.types import ContextEntry

_DEFAULT_MAX_PER_GROUP = 20
_DEFAULT_MAX_AGE_SECONDS = 3600.0


class GroupContextBuffer:
    """Per-group ring buffer that accumulates non-trigger messages.

    Thread-safety: not required — all access is from the single-threaded
    asyncio event loop via AgentRouter.
    """

    __slots__ = ("_drained_at", "_max_age", "_max_per_group", "_store")

    def __init__(
        self,
        max_per_group: int = _DEFAULT_MAX_PER_GROUP,
        max_age_seconds: float = _DEFAULT_MAX_AGE_SECONDS,
    ) -> None:
        self._store: dict[str, deque[ContextEntry]] = {}
        # (channel, chat_id) -> when its persisted context was last taken; what a turn took is in its transcript.
        self._drained_at: dict[tuple[str, str], datetime] = {}
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

    async def drain_async(self, channel: str, chat_id: str) -> tuple[ContextEntry, ...]:
        """Asynchronously load context from persistent data plane with in-memory fallback."""
        taken_at = datetime.now(timezone.utc)
        since = taken_at - timedelta(seconds=self._max_age)
        last_taken_at = self._drained_at.get((channel, chat_id))
        if last_taken_at is not None and last_taken_at > since:
            since = last_taken_at
        try:
            from app.channels.routing.channel_data_plane import ChannelDataPlaneService

            persisted = await ChannelDataPlaneService.get_recent_context_entries(
                channel=channel,
                chat_id=chat_id,
                limit=self._max_per_group,
                since=since,
            )
            if persisted:
                # Clear in-memory buffer only when the data plane actually answered, so an
                # empty result cannot discard context the in-memory buffer still holds.
                self._store.pop(chat_id, None)
                self._drained_at[(channel, chat_id)] = taken_at
                return tuple(persisted)
        except Exception:
            pass

        # Fallback to local memory buffer if DB query fails or empty
        return self.drain(chat_id)

    def clear(self, chat_id: str) -> None:
        """Explicitly clear a group's buffer (e.g. when group is disabled)."""
        self._store.pop(chat_id, None)
        self._drained_at = {key: at for key, at in self._drained_at.items() if key[1] != chat_id}

    def clear_all(self) -> None:
        """Clear all buffers (e.g. on shutdown)."""
        self._store.clear()
        self._drained_at.clear()
