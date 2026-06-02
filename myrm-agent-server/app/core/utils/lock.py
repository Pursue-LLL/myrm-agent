"""Standalone Lock Provider Implementation

[INPUT]
(none — self-contained async lock using stdlib)

[OUTPUT]
StandaloneLockProvider: Per-key async lock for single-process standalone environments
MemoryAsyncLockProvider: Alias for StandaloneLockProvider

[POS]
进程内异步锁提供者。为独立/沙箱单进程环境中的共享资源
（SQLite、Skills、Cron）提供互斥保护。
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class StandaloneLockProvider:
    """Per-key async lock for single-process standalone environments.

    Each unique key gets its own asyncio.Lock, providing safe concurrent
    access to shared resources within a single process.
    """

    def __init__(self, **_kwargs: object) -> None:
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def acquire(self, key: str, timeout: float = 30.0) -> AsyncGenerator[None, None]:
        lock = self._locks[key]
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Failed to acquire lock '{key}' within {timeout}s") from None
        try:
            yield
        finally:
            lock.release()


MemoryAsyncLockProvider = StandaloneLockProvider
