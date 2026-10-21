"""Background Maintenance Daemon.

A truly zero-blocking worker queue that handles memory flushing, consolidation,
and skill review extraction asynchronously, preventing UI spin-locks at the end
of agent sessions.

- Bounded queue (maxsize=512) prevents unbounded memory growth under load.
- Idempotent start() via asyncio.Lock prevents double-start races.
- Graceful shutdown with timeout and queue drain.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine

logger = logging.getLogger(__name__)

_MAX_QUEUE_SIZE = 512


class MaintenanceDaemon:
    """Zero-blocking background worker for heavy post-session tasks."""

    def __init__(self, max_queue_size: int = _MAX_QUEUE_SIZE) -> None:
        self._queue: asyncio.Queue[Callable[[], Coroutine[None, None, None]]] = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: asyncio.Task[None] | None = None
        self._start_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the background worker (idempotent, safe for concurrent callers)."""
        if self._worker_task is not None and not self._worker_task.done():
            return
        async with self._start_lock:
            # Double-check after acquiring lock
            if self._worker_task is not None and not self._worker_task.done():
                return
            self._worker_task = asyncio.create_task(self._worker())
            logger.info("MaintenanceDaemon started")

    async def stop(self, timeout_seconds: float = 5.0) -> None:
        """Stop the background worker gracefully.

        Waits for the queue to empty before cancelling the worker, preventing
        data loss of queued memory/skill extraction tasks.
        """
        if self._worker_task:
            logger.info(
                "MaintenanceDaemon shutting down... waiting for %d tasks to complete",
                self._queue.qsize(),
            )

            try:
                await asyncio.wait_for(self._queue.join(), timeout=timeout_seconds)
                logger.info("MaintenanceDaemon queue cleared successfully")
            except asyncio.TimeoutError:
                logger.warning(
                    "MaintenanceDaemon shutdown timed out after %.1fs, some tasks may be lost",
                    timeout_seconds,
                )

            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            logger.info("MaintenanceDaemon stopped")

    def submit(self, task_func: Callable[[], Coroutine[None, None, None]]) -> None:
        """Submit a coroutine function to the background queue.

        Raises QueueFull if the daemon is overloaded (bounded queue).
        """
        try:
            self._queue.put_nowait(task_func)
            logger.debug("Task submitted to MaintenanceDaemon queue (depth=%d)", self._queue.qsize())
        except asyncio.QueueFull:
            logger.error(
                "MaintenanceDaemon queue full (max=%d), dropping task. "
                "Consider increasing max_queue_size or reducing submit rate.",
                self._queue.maxsize,
            )
            raise

    async def _worker(self) -> None:
        """Background worker loop."""
        while True:
            task_func = await self._queue.get()
            try:
                await task_func()
            except Exception as e:
                logger.error("Error executing background task in MaintenanceDaemon: %s", e, exc_info=True)
            finally:
                self._queue.task_done()

    @property
    def queue_depth(self) -> int:
        """Current number of pending tasks (for monitoring)."""
        return self._queue.qsize()


# Global singleton instance
maintenance_daemon = MaintenanceDaemon()
