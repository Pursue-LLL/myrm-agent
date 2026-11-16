"""Per-session goal queue index over StorageProvider.

[INPUT]
- toolkits.storage.base::StorageProvider (POS: Storage protocol)
- .types::Goal (POS: Goal data types)

[OUTPUT]
- GoalQueueIndex: the entries (goal id, priority, creation time) of the goals queued behind a session's active
  goal. Every change is a read-modify-write serialized per session, and a queue that cannot be read is never
  replaced by an empty one.

[POS]
Persists one session's goal queue as a single JSON list; GoalStorage fronts it for the goal manager.
"""

from __future__ import annotations

import asyncio
import json
import logging
import weakref
from typing import TYPE_CHECKING

from .types import Goal

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.storage.base import StorageProvider

logger = logging.getLogger(__name__)

# Adding (IM, cron), cancelling and reordering (goals panel) and dequeuing the next goal run as separate tasks, and
# each is a read-modify-write of one document: unserialized, a write-back erases a change made while it was being
# prepared. The lock is per process, which is enough because the server runs as one process; it is keyed by session
# alone because a process holds one goal storage. Weak values let a session's lock go once no task uses it.
_SESSION_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def _session_lock(session_id: str) -> asyncio.Lock:
    return _SESSION_LOCKS.setdefault(session_id, asyncio.Lock())


class GoalQueueIndex:
    """The queue of one storage, one JSON document per session under `{key_prefix}/{session_id}`."""

    def __init__(self, storage: StorageProvider, key_prefix: str) -> None:
        self._storage = storage
        self._key_prefix = key_prefix

    async def read(self, session_id: str) -> list[dict[str, object]]:
        """Return the entries in queue order; a missing queue is empty and one that cannot be read raises.

        Every change writes the queue back, so an empty stand-in for a queue that failed to read would replace
        it. Content that is not a JSON list is the exception: it is logged and read as empty, because the next
        write is the only way to repair it.
        """
        try:
            raw = await self._storage.read(key=self._key(session_id))
        except FileNotFoundError:
            return []
        if not raw:
            return []
        try:
            queue = json.loads(raw.decode("utf-8"))
        except ValueError:
            queue = None
        if not isinstance(queue, list):
            logger.error(
                "Goal queue of session %r is not a JSON list (%d bytes) and is read as empty", session_id, len(raw)
            )
            return []
        return queue

    async def add(self, goal: Goal) -> None:
        """Insert a goal at the place its priority and creation time give it."""
        entry: dict[str, object] = {
            "goal_id": goal.goal_id,
            "priority": goal.priority,
            "created_at": goal.created_at.isoformat(),
        }
        async with _session_lock(goal.session_id):
            queue = await self.read(goal.session_id)
            queue.append(entry)
            queue.sort(key=lambda e: (e["priority"], e["created_at"]))
            await self._write(goal.session_id, queue)

    async def remove(self, session_id: str, goal_id: str) -> None:
        """Drop a goal from the queue."""
        async with _session_lock(session_id):
            queue = await self.read(session_id)
            await self._write(session_id, [e for e in queue if e["goal_id"] != goal_id])

    async def reorder(self, session_id: str, ordered_goal_ids: list[str]) -> None:
        """Give the listed goals the priorities of their positions; goals not listed follow in their current order."""
        async with _session_lock(session_id):
            queue = await self.read(session_id)
            id_to_entry = {e["goal_id"]: e for e in queue}
            reordered: list[dict[str, object]] = []
            for i, gid in enumerate(ordered_goal_ids):
                if gid in id_to_entry:
                    entry = id_to_entry.pop(gid)
                    entry["priority"] = i
                    reordered.append(entry)
            for entry in id_to_entry.values():
                entry["priority"] = len(reordered)
                reordered.append(entry)
            await self._write(session_id, reordered)

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}/{session_id}"

    async def _write(self, session_id: str, queue: list[dict[str, object]]) -> None:
        await self._storage.write(key=self._key(session_id), content=json.dumps(queue).encode("utf-8"))
