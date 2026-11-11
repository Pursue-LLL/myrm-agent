"""In-flight request limiter for preventing concurrent storms.

Difference from Rate Limiting:
- Rate Limiting: caps the request frequency (requests per minute)
- In-Flight Limiting: caps the concurrency (number of requests processed simultaneously)

[INPUT]

[OUTPUT]
- InFlightLimiter: Concurrency control protocol
- MemoryInFlightLimiter: In-memory concurrency limiter (framework default implementation)

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
    """Concurrency control protocol

    Limits the number of concurrent requests per identifier (e.g. IP) to prevent concurrent storms.
    Uses the Context Manager pattern to guarantee that the counter is released correctly.

    Example:
        >>> limiter = MemoryInFlightLimiter(max_concurrent=8)
        >>> async with limiter.acquire("192.168.1.100") as acquired:
        ...     if not acquired:
        ...         raise TooManyConcurrentRequests()
        ...     # Process the request
        >>> # The count is released automatically by the finally block
    """

    @asynccontextmanager
    async def acquire(self, identifier: str) -> AsyncIterator[bool]:
        """Acquire a concurrency slot (Context Manager)

        Args:
            identifier: Client identifier (usually an IP address)

        Yields:
            bool: True if acquired, False if the concurrency limit is exceeded

        Example:
            >>> async with limiter.acquire("203.0.113.45") as acquired:
            ...     if not acquired:
            ...         return JSONResponse({"error": "too many concurrent requests"}, 429)
            ...     await process_request()
        """
        ...


class MemoryInFlightLimiter:
    """In-memory concurrency limiter (framework default implementation)

    Tracks the current concurrency of each identifier with a counter.
    The Context Manager guarantees the count is released correctly even when an exception occurs.

    Example:
        >>> limiter = MemoryInFlightLimiter(max_concurrent=8)
        >>> async with limiter.acquire("192.168.1.100") as acquired:
        ...     if acquired:
        ...         await handle_webhook()
    """

    def __init__(self, max_concurrent: int = 8) -> None:
        """Initialize the concurrency limiter

        Args:
            max_concurrent: Maximum concurrency allowed per identifier (default 8)
        """
        self._max_concurrent = max_concurrent
        self._counters: dict[str, int] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, identifier: str) -> AsyncIterator[bool]:
        """Acquire a concurrency slot (released automatically)

        Args:
            identifier: Client identifier (e.g. IP address)

        Yields:
            bool: True=acquired, False=concurrency limit exceeded
        """
        acquired = False

        try:
            # Try to acquire a slot
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
            # Release the slot automatically (runs even when an exception occurs)
            if acquired:
                async with self._lock:
                    self._counters[identifier] -= 1
                    if self._counters[identifier] <= 0:
                        del self._counters[identifier]  # Clean up zero counts
                    logger.debug(
                        f"In-flight slot released: {identifier}",
                        extra={"identifier": identifier},
                    )

    def get_current_count(self, identifier: str) -> int:
        """Get the current concurrency (for monitoring/debugging only)."""
        return self._counters.get(identifier, 0)

    def get_total_in_flight(self) -> int:
        """Get the total concurrency across all identifiers (for monitoring only)."""
        return sum(self._counters.values())
