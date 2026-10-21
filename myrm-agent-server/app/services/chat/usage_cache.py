"""In-process TTL cache for per-chat usage aggregation.

[INPUT]
- Chat.total_* columns (POS: O(1) 用量聚合缓存列，由 assistant 消息 extra_data 快照重建)

[OUTPUT]
- ChatUsageCache (POS: 进程内短窗口去抖缓存，TTL 过期后重新聚合)

[POS]
用量聚合去抖层。The Chat.total_* columns are an O(1) usage cache rebuilt from
assistant message extra_data snapshots. Within one long-running session
consecutive turns trigger one sync each; without caching every sync would
re-aggregate the whole chat. This module debounces those rebuilds within a
short window while still guaranteeing fresh values on TTL expiry. Entries are
bounded to prevent unbounded growth in long-running processes.

Freshness is keyed on the last aggregated assistant message id: a cached
aggregate is only reused when no new (or differently-active) assistant message
has been added, so the final message of a turn is never missed and sibling
switches invalidate the cache.
"""

from __future__ import annotations

import time

_TTL_SECONDS = 5
_MAX_ENTRIES = 4096


class ChatUsageCache:
    def __init__(
        self,
        ttl_seconds: float = _TTL_SECONDS,
        max_entries: int = _MAX_ENTRIES,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._touched_at: dict[str, float] = {}
        self._last_message_ids: dict[str, str | None] = {}
        self._values: dict[str, dict[str, int | float]] = {}

    def get(self, chat_id: str, last_message_id: str | None) -> dict[str, int | float] | None:
        """Return the cached aggregate if it is fresh and covers the same messages."""
        touched = self._touched_at.get(chat_id)
        if touched is None:
            return None
        if time.monotonic() - touched >= self._ttl_seconds:
            self._touched_at.pop(chat_id, None)
            self._last_message_ids.pop(chat_id, None)
            self._values.pop(chat_id, None)
            return None
        if self._last_message_ids.get(chat_id) != last_message_id:
            return None
        return self._values.get(chat_id)

    def set(
        self,
        chat_id: str,
        last_message_id: str | None,
        value: dict[str, int | float],
    ) -> None:
        if chat_id not in self._touched_at and len(self._touched_at) >= self._max_entries:
            oldest = min(self._touched_at, key=self._touched_at.get)
            self._touched_at.pop(oldest, None)
            self._last_message_ids.pop(oldest, None)
            self._values.pop(oldest, None)
        self._touched_at[chat_id] = time.monotonic()
        self._last_message_ids[chat_id] = last_message_id
        self._values[chat_id] = value

    def invalidate(self, chat_id: str) -> None:
        self._touched_at.pop(chat_id, None)
        self._last_message_ids.pop(chat_id, None)
        self._values.pop(chat_id, None)
