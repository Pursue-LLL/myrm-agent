"""Inbound rate limiting for webhook endpoints.

 and 出站限流（rate_limiter.py）职责 not 同：
- 出站限流： prevent 平台封禁（per-channel Token Bucket）
- 入站限流： prevent DoS攻击（per-IP/per-endpoint Token Bucket）

[INPUT]

[OUTPUT]
- InboundRateLimiter: 入站限流Protocol
- MemoryInboundLimiter: 内存限流器（框架Defaultimplements）

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
    """入站限流Protocol"""

    async def check_limit(
        self,
        identifier: str,
        endpoint: str,
        limit_per_minute: int = 60,
    ) -> bool:
        """CheckWhether超过限流

        Returns:
            True表示 allow ，False表示超限
        """
        ...


class TokenBucket:
    """Token Bucket限流算法（单机内存implements）"""

    __slots__ = ("_burst", "_last_refill", "_lock", "_rate", "_tokens")

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        """尝试Gettoken（非blocking）"""
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
    """内存入站限流器（框架Defaultimplements）"""

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
        """Check入站RequestWhether超限"""
        key = f"{endpoint}:{identifier}"

        with self._lock:
            if key not in self._buckets:
                rate_per_sec = limit_per_minute / 60.0
                burst = max(1, int(limit_per_minute / 6))
                self._buckets[key] = TokenBucket(rate=rate_per_sec, burst=burst)

        bucket = self._buckets[key]
        return await bucket.try_acquire()

    def cleanup_stale_buckets(self, max_age_seconds: int = 3600) -> int:
        """Clean up长期 not yet  using  bucket（optional，节省内存）"""
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
    """Create入站限流器（工厂Function）"""
    if backend == "memory":
        return MemoryInboundLimiter(**kwargs)  # type: ignore[arg-type]

    msg = f"Unsupported inbound limiter backend: {backend}"
    raise ValueError(msg)
