"""Rate limiting for inbound messages.

Prevents cost explosion by limiting message processing frequency per sender/chat.
Uses sliding window algorithm for smooth rate distribution.

[INPUT]
- app.channels.types::InboundMessage (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- RateLimitConfig: Rate limit configuration.
- RateLimiter: Sliding window rate limiter for inbound messages.

[POS]
Rate limiting for inbound messages.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

from app.channels.types import InboundMessage

logger = logging.getLogger(__name__)

ScopeType = Literal["sender", "chat", "global"]


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """Rate limit configuration."""

    max_requests: int = 10
    window_seconds: float = 60.0
    scope: ScopeType = "sender"
    enabled: bool = True


class RateLimiter:
    """Sliding window rate limiter for inbound messages.

    Tracks request timestamps per scope (sender/chat/global) and
    enforces max_requests per window_seconds limit.

    Thread-safe using asyncio.Lock to prevent race conditions.
    """

    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self._timestamps: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check_and_update(self, msg: InboundMessage) -> bool:
        """Check if message passes rate limit and update state.

        Returns:
            True if message is allowed, False if rate limited.
        """
        if not self.config.enabled:
            return True

        async with self._lock:
            key = self._get_scope_key(msg)
            now = time.monotonic()

            if key not in self._timestamps:
                self._timestamps[key] = deque()

            window = self._timestamps[key]
            cutoff = now - self.config.window_seconds

            while window and window[0] < cutoff:
                window.popleft()

            if len(window) >= self.config.max_requests:
                logger.warning(
                    "Rate limit exceeded for %s (scope=%s, %d/%d in %.1fs)",
                    key,
                    self.config.scope,
                    len(window),
                    self.config.max_requests,
                    self.config.window_seconds,
                )
                return False

            window.append(now)
            return True

    def _get_scope_key(self, msg: InboundMessage) -> str:
        """Extract rate limit scope key from message."""
        if self.config.scope == "global":
            return "global"
        if self.config.scope == "chat":
            return msg.chat_id
        return msg.sender_id

    def reset(self, key: str | None = None) -> None:
        """Reset rate limit state for a specific key or all keys."""
        if key is None:
            self._timestamps.clear()
        elif key in self._timestamps:
            del self._timestamps[key]


DISABLED_RATE_LIMIT = RateLimitConfig(enabled=False)

DEFAULT_RATE_LIMIT = RateLimitConfig(
    max_requests=10,
    window_seconds=60.0,
    scope="sender",
    enabled=True,
)

STRICT_RATE_LIMIT = RateLimitConfig(
    max_requests=5,
    window_seconds=60.0,
    scope="sender",
    enabled=True,
)
