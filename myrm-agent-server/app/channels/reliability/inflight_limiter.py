"""In-flight request limiter for preventing concurrent storms.

 and Rate Limiting 区别：
- Rate Limiting: 限制Request频率（每分钟Request数）
- In-Flight Limiting: 限制ConcurrentCount（ simultaneously Process Request数）

[INPUT]

[OUTPUT]
- InFlightLimiter: Concurrent控制Protocol
- MemoryInFlightLimiter: 内存Concurrent限制器（框架Defaultimplements）

[POS]
Concurrency control layer. Prevents resource exhaustion from concurrent request storms.
Uses Semaphore pattern with guaranteed count release via Context Manager.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

logger = logging.getLogger(__name__)


class InFlightLimiter(Protocol):
    """Concurrent控制Protocol

    限制同一标识符（如IP） ConcurrentRequestCount， prevent Concurrent风暴。
     using Context ManagerMode guarantee 计数器正确Release。

    Example:
        >>> limiter = MemoryInFlightLimiter(max_concurrent=8)
        >>> async with limiter.acquire("192.168.1.100") as acquired:
        ...     if not acquired:
        ...         raise TooManyConcurrentRequests()
        ...     # ProcessRequest
        >>> # finally块AutoRelease计数
    """

    @asynccontextmanager
    async def acquire(self, identifier: str) -> AsyncIterator[bool]:
        """GetConcurrent槽位（Context Manager）

        Args:
            identifier: Client标识符（usually是IPAddress）

        Yields:
            bool: True表示GetSuccess，False表示超过Concurrent限制

        Example:
            >>> async with limiter.acquire("203.0.113.45") as acquired:
            ...     if not acquired:
            ...         return JSONResponse({"error": "too many concurrent requests"}, 429)
            ...     await process_request()
        """
        ...


class MemoryInFlightLimiter:
    """内存Concurrent限制器（框架Defaultimplements）

     using 计数器Mode，跟踪Each标识符 CurrentConcurrent数。
    Context Manager guarantee Exception时也能正确Release计数。

    Example:
        >>> limiter = MemoryInFlightLimiter(max_concurrent=8)
        >>> async with limiter.acquire("192.168.1.100") as acquired:
        ...     if acquired:
        ...         await handle_webhook()
    """

    def __init__(self, max_concurrent: int = 8) -> None:
        """InitializeConcurrent限制器

        Args:
            max_concurrent: Each标识符 allow  MaximumConcurrent数（Default8）
        """
        self._max_concurrent = max_concurrent
        self._counters: dict[str, int] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, identifier: str) -> AsyncIterator[bool]:
        """GetConcurrent槽位（AutoRelease）

        Args:
            identifier: Client标识符（如IPAddress）

        Yields:
            bool: True=GetSuccess，False=超过Concurrent限制
        """
        acquired = False

        try:
            # 尝试Get槽位
            async with self._lock:
                current = self._counters.get(identifier, 0)
                if current < self._max_concurrent:
                    self._counters[identifier] = current + 1
                    acquired = True
                    logger.debug(
                        f"In-flight slot acquired: {identifier} ({current + 1}/{self._max_concurrent})",
                        extra={"identifier": identifier, "in_flight": current + 1},
                    )
                else:
                    logger.warning(
                        f"In-flight limit exceeded: {identifier} ({current}/{self._max_concurrent})",
                        extra={"identifier": identifier, "limit": self._max_concurrent},
                    )

            yield acquired

        finally:
            # AutoRelease槽位（i.e.使Exception也会Execute）
            if acquired:
                async with self._lock:
                    self._counters[identifier] -= 1
                    if self._counters[identifier] <= 0:
                        del self._counters[identifier]  # Clean up零计数
                    logger.debug(
                        f"In-flight slot released: {identifier}",
                        extra={"identifier": identifier},
                    )

    def get_current_count(self, identifier: str) -> int:
        """GetCurrentConcurrent数（Only for 监控/调试）"""
        return self._counters.get(identifier, 0)

    def get_total_in_flight(self) -> int:
        """GetAll标识符 总Concurrent数（Only for 监控）"""
        return sum(self._counters.values())
