"""SSE events for real-time task status updates."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from myrm_agent_harness.toolkits.tasks import TaskStatus

logger = logging.getLogger(__name__)


class TaskEventBus:
    """Event bus for task status updates.

    Broadcasts task events to all SSE subscribers in real-time.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, object]]:
        """Subscribe to task events."""
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        """Unsubscribe from task events."""
        self._subscribers.discard(queue)

    async def emit(self, task_id: str, status: TaskStatus, data: dict[str, object] | None = None) -> None:
        """Emit task event to all subscribers."""
        event: dict[str, object] = {
            "task_id": task_id,
            "status": status.value,
            "timestamp": asyncio.get_event_loop().time(),
        }

        if data:
            event.update(data)

        # Broadcast to all subscribers (non-blocking)
        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Subscriber queue full, dropping event for task {task_id}")
            except Exception as e:
                logger.error(f"Failed to emit event to subscriber: {e}")
                dead_queues.append(queue)

        # Remove dead subscribers
        for queue in dead_queues:
            self._subscribers.discard(queue)

    async def stream_events(self) -> AsyncGenerator[str, None]:
        """Generate SSE stream for subscriber.

        Yields SSE-formatted events.
        """
        queue = self.subscribe()
        try:
            while True:
                event = await queue.get()
                yield f"event: task_update\ndata: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(queue)


# Global event bus (singleton)
task_event_bus = TaskEventBus()

__all__ = ["TaskEventBus", "task_event_bus"]
