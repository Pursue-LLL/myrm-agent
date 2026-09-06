"""Thread-safe in-memory task repository for A2A tasks.

Manages task records, transitions through the A2A task lifecycle,
and provides automatic capacity bounding to avoid memory exhaustion.

[INPUT]
- A2ATask instances, state updates

[OUTPUT]
- A2ATask queries and lifecycle updates

[POS]
Task state persistence layer for A2A Provider Server.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict

from myrm_agent_harness.toolkits.a2a.types import (
    A2ATask,
    TaskArtifact,
    TaskMessage,
    TaskRole,
    TaskStatus,
)

_TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}


class A2ATaskStore:
    """Thread-safe, bounded in-memory store for A2A tasks."""

    def __init__(self, max_capacity: int = 1000) -> None:
        self._max_capacity = max_capacity
        self._tasks: OrderedDict[str, A2ATask] = OrderedDict()
        self._lock = asyncio.Lock()

    async def create_task(self, task: A2ATask) -> A2ATask:
        """Register a new task in the store."""
        async with self._lock:
            # Evict oldest terminal tasks if over capacity
            if len(self._tasks) >= self._max_capacity:
                self._evict_oldest_terminal_unlocked()

            self._tasks[task.task_id] = task
            return task

    async def get_task(self, task_id: str) -> A2ATask | None:
        """Fetch task by ID."""
        async with self._lock:
            return self._tasks.get(task_id)

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        error: str | None = None,
        agent_message: str | None = None,
        artifacts: list[TaskArtifact] | None = None,
    ) -> A2ATask | None:
        """Perform a validated lifecycle state transition."""
        async with self._lock:
            current = self._tasks.get(task_id)
            if current is None:
                return None

            # Disallow transitions from terminal states
            if current.status in _TERMINAL_STATUSES:
                return current

            now = time.time()
            messages = list(current.messages)
            if agent_message:
                messages.append(
                    TaskMessage(role=TaskRole.AGENT, content=agent_message, timestamp=now)
                )

            new_artifacts = list(current.artifacts)
            if artifacts:
                new_artifacts.extend(artifacts)

            updated = A2ATask(
                task_id=current.task_id,
                status=status,
                messages=messages,
                artifacts=new_artifacts,
                created_at=current.created_at,
                updated_at=now,
                error=error or current.error,
                agent_id=current.agent_id,
                push_url=current.push_url,
                push_secret=current.push_secret,
            )
            self._tasks[task_id] = updated
            # Move to end of OrderedDict for LRU-style tracking
            self._tasks.move_to_end(task_id)
            return updated

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel an in-flight task."""
        async with self._lock:
            current = self._tasks.get(task_id)
            if current is None or current.status in _TERMINAL_STATUSES:
                return False

            now = time.time()
            cancelled = A2ATask(
                task_id=current.task_id,
                status=TaskStatus.CANCELLED,
                messages=current.messages,
                artifacts=current.artifacts,
                created_at=current.created_at,
                updated_at=now,
                error="Task cancelled by caller request.",
                agent_id=current.agent_id,
                push_url=current.push_url,
                push_secret=current.push_secret,
            )
            self._tasks[task_id] = cancelled
            self._tasks.move_to_end(task_id)
            return True

    def _evict_oldest_terminal_unlocked(self) -> None:
        """Evict oldest terminal task to make room; if none, evicts oldest entry."""
        for tid, task in list(self._tasks.items()):
            if task.status in _TERMINAL_STATUSES:
                del self._tasks[tid]
                return
        if self._tasks:
            self._tasks.popitem(last=False)
