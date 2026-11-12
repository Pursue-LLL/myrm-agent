"""Inbound rate limiting for webhook endpoints.

Its responsibility differs from outbound rate limiting (rate_limiter.py):
- Outbound limiting: prevents platform bans (per-channel Token Bucket)
- Inbound limiting: prevents DoS attacks (per-IP/per-endpoint Token Bucket)

[INPUT]
- none (imports no other project module)

[OUTPUT]
- InboundRateLimiter: Inbound rate limiting protocol
- MemoryInboundLimiter: In-memory rate limiter (framework default implementation)

[POS]
Inbound rate limiting layer. Prevents DoS/DDoS attacks on webhook endpoints.
Framework provides in-memory implementation; business layer can inject Redis for distributed mode.
"""

from __future__ import annotations

import asyncio
import time
from threading import Lock
from typing import Protocol


class InboundRateLimiter(Protocol):
    """Inbound rate limiting protocol."""

    async def check_limit(
        self,
        identifier: str,
        endpoint: str,
        limit_per_minute: int = 60,
    ) -> bool:
        """Check whether the rate limit is exceeded

        Returns:
            True if the request is allowed, False if the limit is exceeded
        """
        ...


class TokenBucket:
    """Token Bucket rate limiting algorithm (single-process in-memory implementation)."""

    __slots__ = ("_burst", "_last_refill", "_lock", "_rate", "_tokens")

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        """Try to get a token (non-blocking)."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True

            return False


class MemoryInboundLimiter:
    """In-memory inbound rate limiter (framework default implementation)."""

    def __init__(self, default_rate: float = 60.0) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._default_rate = default_rate
        self._lock = Lock()

    async def check_limit(
        self,
        identifier: str,
        endpoint: str,
        limit_per_minute: int = 60,
    ) -> bool:
        """Check whether an inbound request exceeds the limit."""
        key = f"{endpoint}:{identifier}"

        with self._lock:
            if key not in self._buckets:
                rate_per_sec = limit_per_minute / 60.0
                burst = max(1, int(limit_per_minute / 6))
                self._buckets[key] = TokenBucket(rate=rate_per_sec, burst=burst)

        bucket = self._buckets[key]
        return await bucket.try_acquire()

    def cleanup_stale_buckets(self, max_age_seconds: int = 3600) -> int:
        """Clean up buckets that have not been used for a long time (optional, saves memory)."""
        with self._lock:
            now = time.monotonic()
            stale_keys = [key for key, bucket in self._buckets.items() if (now - bucket._last_refill) > max_age_seconds]

            for key in stale_keys:
                del self._buckets[key]

            return len(stale_keys)


def create_inbound_limiter(
    backend: str = "memory",
    **kwargs: object,
) -> InboundRateLimiter:
    """Create an inbound rate limiter (factory function)."""
    if backend == "memory":
        return MemoryInboundLimiter(**kwargs)  # type: ignore[arg-type]

    msg = f"Unsupported inbound limiter backend: {backend}"
    raise ValueError(msg)
