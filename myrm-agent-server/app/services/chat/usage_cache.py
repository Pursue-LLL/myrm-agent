"""In-process TTL cache for per-chat usage aggregation.

The Chat.total_* columns are an O(1) usage cache rebuilt from assistant
message extra_data snapshots. Within one long-running session consecutive
turns trigger one sync each; without caching every sync would re-aggregate
the whole chat. This module debounces those rebuilds within a short window
while still guaranteeing fresh values on TTL expiry.
"""

from __future__ import annotations

import time

_TTL_SECONDS = 5


class ChatUsageCache:
    def __init__(self, ttl_seconds: float = _TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._touched_at: dict[str, float] = {}
        self._values: dict[str, dict[str, int | float]] = {}

    def get(self, chat_id: str) -> dict[str, int | float] | None:
        """Return the cached aggregate if it is still fresh, else None."""
        touched = self._touched_at.get(chat_id)
        if touched is None:
            return None
        if time.monotonic() - touched >= self._ttl_seconds:
            self._touched_at.pop(chat_id, None)
            self._values.pop(chat_id, None)
            return None
        return self._values.get(chat_id)

    def set(self, chat_id: str, value: dict[str, int | float]) -> None:
        self._touched_at[chat_id] = time.monotonic()
        self._values[chat_id] = value

    def invalidate(self, chat_id: str) -> None:
        self._touched_at.pop(chat_id, None)
        self._values.pop(chat_id, None)
