"""Per-channel token bucket rate limiter.

Prevents platform bans by throttling outbound message frequency.
Each channel gets its own bucket with platform-specific limits.

[INPUT]
(no external dependencies, pure asyncio implementation)

[OUTPUT]
- ChannelRateLimiter: Token bucket ratelimit

[POS]
Per-channel outbound rate limiting. Prevents platform bans due to excessive send frequency.
"""

from __future__ import annotations

import asyncio
import math
import time

_CHANNEL_RATES: dict[str, float] = {
    "whatsapp": 2.0,
    "telegram": 20.0,
    "slack": 1.0,
    "discord": 5.0,
    "teams": 4.0,
    "feishu": 5.0,
    "dingtalk": 5.0,
    "wecom": 4.0,
}
_DEFAULT_RATE = 10.0


class TokenBucket:
    """Async token bucket — ``acquire()`` blocks until a token is available."""

    __slots__ = ("_burst", "_last_refill", "_lock", "_rate", "_tokens")

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume one."""
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
                self._last_refill = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                wait = (1.0 - self._tokens) / self._rate

            # Sleep outside the lock so other coroutines can proceed
            await asyncio.sleep(wait)


def create_limiter(channel_name: str) -> TokenBucket:
    """Create a rate limiter tuned for *channel_name*."""
    rate = _CHANNEL_RATES.get(channel_name, _DEFAULT_RATE)
    burst = max(1, math.ceil(rate / 2))
    return TokenBucket(rate, burst)
