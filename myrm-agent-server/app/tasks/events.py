"""SSE events for real-time task status updates.

[INPUT]
- myrm_agent_harness.toolkits.tasks::TaskStatus (POS: Queue protocol + compare-and-set persistence contract)
- app/tasks/metrics.py::{safe_counter_inc, task_event_emitted_total, task_event_dropped_total, task_event_replaced_total} (POS: Prometheus instruments and best-effort recorders for the task subsystem)

[OUTPUT]
- TaskEventBus: in-memory fan-out of task status events to SSE subscribers through bounded per-subscriber queues.
- task_event_bus: the process-wide bus; the worker callback and the cancel endpoint publish to it, the SSE endpoint streams from it.

[POS]
- SSE task status event hub. When a subscriber queue is full the oldest buffered event is replaced by the newest one flagged
  ``sync_required``, so a slow client resynchronises instead of falling further behind; delivery counters never affect delivery.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable

from myrm_agent_harness.toolkits.tasks import TaskStatus

from app.tasks.metrics import (
    safe_counter_inc,
    task_event_dropped_total,
    task_event_emitted_total,
    task_event_replaced_total,
)

logger = logging.getLogger(__name__)


class TaskEventBus:
    """Event bus for task status updates.

    Broadcasts task events to all SSE subscribers in real-time.
    """

    def __init__(
        self,
        *,
        queue_full_warning_interval_seconds: float = 10.0,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()
        self._queue_full_warning_interval_seconds = max(queue_full_warning_interval_seconds, 0.0)
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._next_queue_full_warning_at = 0.0
        self._suppressed_queue_full_warnings = 0

    def _warn_queue_full(self, task_id: str, action: str) -> None:
        if self._queue_full_warning_interval_seconds <= 0:
            logger.warning("Subscriber queue full, %s for task %s", action, task_id)
            return

        now = self._monotonic_clock()
        if now < self._next_queue_full_warning_at:
            self._suppressed_queue_full_warnings += 1
            return

        suppressed = self._suppressed_queue_full_warnings
        self._suppressed_queue_full_warnings = 0
        self._next_queue_full_warning_at = now + self._queue_full_warning_interval_seconds
        suffix = f" (suppressed {suppressed} similar warnings)" if suppressed else ""
        logger.warning("Subscriber queue full, %s for task %s%s", action, task_id, suffix)

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
                safe_counter_inc(task_event_emitted_total, status=status.value)
            except asyncio.QueueFull:
                safe_counter_inc(task_event_dropped_total, status=status.value, reason="queue_full_drop_oldest")
                overflow_event = dict(event)
                overflow_event["sync_required"] = True
                try:
                    queue.get_nowait()
                    queue.put_nowait(overflow_event)
                    safe_counter_inc(task_event_replaced_total, status=status.value)
                    safe_counter_inc(task_event_emitted_total, status=status.value)
                    self._warn_queue_full(task_id, "replaced oldest buffered event")
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    safe_counter_inc(task_event_dropped_total, status=status.value, reason="queue_full_drop_newest")
                    self._warn_queue_full(task_id, "dropping newest event")
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
