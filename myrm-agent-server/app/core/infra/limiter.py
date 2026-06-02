"""应用层限流器

在 Agent-in-Sandbox 架构下，提供暴力破解防护（WebUI登录、API调用等）。

架构：
- Harness层：通用 RateLimiter（与业务无关）
- Server层：实例化限流器，应用于具体业务场景

防护策略：
- Per-IP限流：同一IP，60秒内最多5次失败
- 全局限流：所有IP合计，60秒内最多100次（防IP伪造/Tor攻击）
- 定期清理：5分钟清理一次过期IP记录（防内存泄漏）
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps

from fastapi import HTTPException, Request, status
from myrm_agent_harness.agent.security.rate_limiter import MemoryRateLimiter, RateLimitConfig

logger = logging.getLogger(__name__)


class RateLimitExceeded(HTTPException):
    """Rate limit exceeded exception."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Please try again in {retry_after_seconds} seconds.",
            headers={"Retry-After": str(retry_after_seconds)},
        )


def _fallback_get_remote_address(request: Request) -> str:
    client = request.client
    return client.host if client else "unknown"


get_remote_address = _fallback_get_remote_address

try:
    from slowapi.util import get_remote_address  # type: ignore[no-redef]
except ImportError:
    pass


class _RateLimiterWrapper:
    """Wrapper for RateLimiter with decorator interface.

    Provides drop-in replacement for slowapi's @limiter.limit() decorator.
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._limiter = MemoryRateLimiter(config)
        self.enabled: bool = True

    def limit(
        self,
        limit_value: str,
        *,
        key_func: Callable[[Request], str] | None = None,
        per_method: bool = True,
        methods: list[str] | None = None,
        error_message: str | None = None,
        exempt_when: Callable[..., bool] | None = None,
        override_defaults: bool = True,
        deduct_when: Callable[..., bool] | None = None,
        on_breach: Callable[..., None] | None = None,
        cost: int | Callable[..., int] = 1,
    ) -> Callable[..., Callable[..., object]]:
        """Rate limit decorator.

        Args:
            limit_value: Limit string (e.g., "5/minute"). Currently ignored,
                         uses RateLimitConfig instead.
            key_func: Function to extract rate limit key from request.
                      Defaults to IP address extraction.
            Other args: Preserved for API compatibility, currently ignored.

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            @wraps(func)
            async def wrapper(*args: object, **kwargs: object) -> object:
                # Extract Request from args
                request: Request | None = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

                if request is None:
                    # No request found, pass through
                    return await func(*args, **kwargs)  # type: ignore[misc]

                # Extract rate limit key (IP address)
                if key_func is not None:
                    key = key_func(request)
                else:
                    key = get_identifier(request)

                # Check rate limit
                result = await self._limiter.check(key)
                if not result.allowed:
                    logger.warning("Rate limit exceeded for key=%s", key)
                    if on_breach is not None:
                        on_breach()
                    raise RateLimitExceeded(retry_after_seconds=result.retry_after_seconds or 60)

                return await func(*args, **kwargs)  # type: ignore[misc]

            return wrapper

        return decorator

    shared_limit = limit

    async def start_cleanup(self) -> None:
        """Start background cleanup task."""
        await self._limiter.start_cleanup_task()

    async def stop_cleanup(self) -> None:
        """Stop background cleanup task."""
        await self._limiter.stop_cleanup_task()


def get_identifier(request: Request) -> str:
    """Extract rate limit identifier from request.

    Prefers user_id (authenticated), falls back to IP address.
    """
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        return f"ip:{client_ip}"

    return f"ip:{get_remote_address(request)}"


# Global rate limiter instance
limiter = _RateLimiterWrapper(
    RateLimitConfig(
        max_attempts_per_key=5,
        max_attempts_global=100,
        window_seconds=60,
        cleanup_interval_seconds=300,
    )
)

__all__ = ["limiter", "get_identifier", "RateLimitExceeded"]
