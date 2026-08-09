"""Adaptive resource yielding for background eval tasks.

[INPUT]
- none

[OUTPUT]
- mark_chat_activity: records a foreground chat activity timestamp.
- AdaptiveEvalManager: async context manager that suspends eval tasks while
  foreground chat activity is recent, yielding CPU/memory to interactive work.

[POS]
Shared concurrency infrastructure for eval orchestration. Used by the single
eval suite, matrix eval, and memory A/B eval.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_last_chat_activity_time: float = 0.0


def mark_chat_activity() -> None:
    """Mark the current time as active chat activity.

    Used by the foreground ChatService to inform the background eval tasks
    to yield CPU/memory resources and avoid blocking.
    """
    global _last_chat_activity_time
    _last_chat_activity_time = time.time()


class AdaptiveEvalManager:
    """Adaptive concurrency manager that yields when chat activity is detected."""

    def __init__(
        self, max_concurrency: int = 3, idle_wait_seconds: float = 3.0
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._idle_wait_seconds = idle_wait_seconds

    async def __aenter__(self) -> None:
        # Always yield briefly to the event loop
        await asyncio.sleep(0.01)

        # If foreground chat activity was detected recently, wait longer to yield resources
        global _last_chat_activity_time
        while time.time() - _last_chat_activity_time < self._idle_wait_seconds:
            logger.debug(
                "Foreground chat activity detected. Suspending eval task briefly..."
            )
            await asyncio.sleep(1.0)

        await self._semaphore.acquire()

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        self._semaphore.release()
