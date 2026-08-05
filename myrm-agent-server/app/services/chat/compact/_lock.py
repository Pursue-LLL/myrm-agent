"""Per-chat compaction locks.

[INPUT]
(none — stdlib only)

[OUTPUT]
- get_compaction_lock: Obtain a per-chat asyncio.Lock (WeakValueDictionary auto-GC)

[POS]
防止同一 chat 并发 compact。锁自动回收，无内存泄漏。
"""

from __future__ import annotations

import asyncio
import weakref

_compaction_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)


def get_compaction_lock(chat_id: str) -> asyncio.Lock:
    lock = _compaction_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _compaction_locks[chat_id] = lock
    return lock
