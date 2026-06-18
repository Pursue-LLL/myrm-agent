"""Support types for inbound policy resolution (cooldown + group follow-up tracking).

[INPUT]
- (stdlib only)

[OUTPUT]
- BoundedCooldownMap: TTL-bounded rate-limit map
- GroupFollowUpTracker: active group thread tracker for mention-exempt follow-up

[POS]
Extracted helpers for PolicyResolver to keep the resolver module under line budget.
"""

from __future__ import annotations

import time

PENDING_REPLY_COOLDOWN = 300.0
PENDING_REPLY_MAX_SIZE = 10000


class BoundedCooldownMap:
    """Bounded map with TTL for rate-limiting, preventing unbounded memory growth under spam."""

    __slots__ = ("_ttl", "_max_size", "_entries")

    def __init__(
        self,
        ttl: float = PENDING_REPLY_COOLDOWN,
        max_size: int = PENDING_REPLY_MAX_SIZE,
    ) -> None:
        self._ttl = ttl
        self._max_size = max_size
        self._entries: dict[str, float] = {}

    def should_suppress(self, key: str) -> bool:
        """Return True if the key is still within cooldown (suppress the action)."""
        now = time.monotonic()
        last = self._entries.get(key)
        if last is not None and now - last < self._ttl:
            return True
        if len(self._entries) >= self._max_size:
            oldest_key = min(self._entries, key=lambda k: self._entries[k])
            self._entries.pop(oldest_key, None)
        self._entries[key] = now
        return False


class GroupFollowUpTracker:
    """Tracks active group threads/conversations for smart exempt-mention follow-up.

    Uses a bounded LRU eviction dict + strictly enforced TTL (10 minutes)
    to prevent memory growth while ensuring microsecond-level query speed.
    """

    def __init__(self, ttl_seconds: float = 600.0, max_size: int = 1000) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._active_threads: dict[str, float] = {}

    def activate(self, key: str) -> None:
        """Mark a thread/conversation as active with LRU eviction."""
        now = time.monotonic()
        if len(self._active_threads) >= self._max_size:
            oldest_key = min(self._active_threads, key=lambda k: self._active_threads[k])
            self._active_threads.pop(oldest_key, None)
        self._active_threads[key] = now

    def is_active(self, key: str) -> bool:
        """Check if active and refresh activity timestamp to keep the session alive."""
        now = time.monotonic()
        last_active = self._active_threads.get(key)
        if last_active is None:
            return False

        if now - last_active > self._ttl:
            self._active_threads.pop(key, None)
            return False

        self._active_threads[key] = now
        return True

    def mute(self, key: str) -> None:
        """Manually mute/deactivate a thread (e.g. via /mute or /shutup command)."""
        self._active_threads.pop(key, None)
