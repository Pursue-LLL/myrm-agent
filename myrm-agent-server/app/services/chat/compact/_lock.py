"""Per-chat compaction locks."""

from __future__ import annotations

import asyncio
import weakref

_compaction_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def get_compaction_lock(chat_id: str) -> asyncio.Lock:
    lock = _compaction_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _compaction_locks[chat_id] = lock
    return lock
