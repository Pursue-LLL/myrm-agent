"""Rate limiting protocol and implementations for custom routes.

Provides framework-agnostic rate limiting abstraction and multiple
implementations for different deployment scenarios.

[INPUT]
- app.channels.core.rate_limit::RateLimitConfig (POS: Rate limiting for inbound messages.)

[OUTPUT]
- RateLimiterProtocol: Framework-agnostic rate limiting interface
- NoOpRateLimiter: No-op implementation for Agent-in-Sandbox (default)
- InMemoryRateLimiter: In-memory sliding window for single-instance sandbox

[POS]
Protocol layer for route-level rate limiting. Enables business layer
to choose appropriate rate limiting strategy based on deployment mode.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Protocol, runtime_checkable

from app.channels.core.rate_limit import RateLimitConfig

logger = logging.getLogger(__name__)


@runtime_checkable
class RateLimiterProtocol(Protocol):
    """Protocol for rate limiting custom route requests.

    Implementations can use different strategies (NoOp, in-memory, Redis)
    based on deployment mode and requirements.
    """

    async def check_limit(
        self,
        route_path: str,
        client_id: str,
        limit_config: RateLimitConfig,
    ) -> tuple[bool, int]:
        """Check if request passes rate limit and update state.

        Args:
            route_path: Full route path (e.g., "/api/channels/telegram/webhook")
            client_id: Client identifier (e.g., IP address, user ID)
            limit_config: Rate limit configuration

        Returns:
            Tuple of (allowed, remaining_requests). If rate limiting is
            disabled or not applicable, returns (True, -1).
        """
        ...


class NoOpRateLimiter:
    """No-op rate limiter for Agent-in-Sandbox environments.

    In Agent-in-Sandbox architecture, each user has an isolated sandbox
    with a dedicated Server instance. Server-layer rate limiting is
    unnecessary (single-user environment). Resource quotas are enforced
    by control plane's ResourceQuota + cgroup limits.

    This is the default implementation for myrm-agent-harness.
    """

    async def check_limit(
        self,
        route_path: str,
        client_id: str,
        limit_config: RateLimitConfig,
    ) -> tuple[bool, int]:
        """Always allow requests (no limiting).

        Returns:
            (True, -1) indicating rate limiting is not enforced
        """
        return (True, -1)


class InMemoryRateLimiter:
    """In-memory sliding window rate limiter.

    Uses deque-based sliding window algorithm for smooth rate distribution.
    Suitable for development environments or single-instance deployments.

    NOT recommended for distributed multi-instance deployments (use Redis).
    """

    def __init__(self) -> None:
        """Initialize rate limiter with empty state."""
        self._timestamps: dict[str, deque[float]] = {}

    async def check_limit(
        self,
        route_path: str,
        client_id: str,
        limit_config: RateLimitConfig,
    ) -> tuple[bool, int]:
        """Check rate limit using sliding window algorithm.

        Args:
            route_path: Full route path
            client_id: Client identifier
            limit_config: Rate limit configuration

        Returns:
            Tuple of (allowed, remaining_requests)
        """
        if not limit_config.enabled:
            return (True, -1)

        key = f"{route_path}:{client_id}"
        now = time.monotonic()

        if key not in self._timestamps:
            self._timestamps[key] = deque()

        window = self._timestamps[key]
        cutoff = now - limit_config.window_seconds

        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= limit_config.max_requests:
            remaining = 0
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "route_path": route_path,
                    "client_id": client_id,
                    "requests": len(window),
                    "max_requests": limit_config.max_requests,
                    "window_seconds": limit_config.window_seconds,
                },
            )
            return (False, remaining)

        window.append(now)
        remaining = limit_config.max_requests - len(window)

        logger.debug(
            "Rate limit check passed",
            extra={
                "route_path": route_path,
                "client_id": client_id,
                "requests": len(window),
                "remaining": remaining,
            },
        )

        return (True, remaining)

    def reset(self, route_path: str | None = None, client_id: str | None = None) -> None:
        """Reset rate limit state for testing.

        Args:
            route_path: Optional route path to reset (resets all if None)
            client_id: Optional client ID to reset (resets all if None)
        """
        if route_path is None and client_id is None:
            self._timestamps.clear()
        elif route_path and client_id:
            key = f"{route_path}:{client_id}"
            if key in self._timestamps:
                del self._timestamps[key]
        else:
            keys_to_delete = [
                k
                for k in self._timestamps.keys()
                if (route_path is None or k.startswith(f"{route_path}:")) and (client_id is None or k.endswith(f":{client_id}"))
            ]
            for key in keys_to_delete:
                del self._timestamps[key]
