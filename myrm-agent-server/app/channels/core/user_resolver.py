"""User resolver protocol and cache for resolving user IDs to display names.

[INPUT]
- channels.core.user_resolver::UserResolver (POS: Generic user resolver protocol and cache implementation. Protocol-first framework design supporting Slack/Feishu/Discord platform extensions with unified username resolution and caching.)
- channels.core.user_resolver::UserResolverCache (POS: Generic user resolver protocol and cache implementation. Protocol-first framework design supporting Slack/Feishu/Discord platform extensions with unified username resolution and caching.)

[OUTPUT]
- UserResolver: Protocol for resolving user IDs to names
- UserResolverCache: Generic LRU+TTL cache with negative caching

[POS]
Generic user resolver protocol and cache implementation. Protocol-first framework design
supporting Slack/Feishu/Discord platform extensions with unified username resolution and caching.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Protocol

logger = logging.getLogger(__name__)


class UserResolver(Protocol):
    """Protocol for resolving user IDs to display names.

    Channel-specific implementations should resolve user IDs via platform APIs
    (e.g., Slack users.info, Feishu user.get) and cache results.

    Example:
        class SlackUserResolver:
            async def resolve_user(self, user_id: str) -> str | None:
                # 1. Check cache
                # 2. Call users.info API
                # 3. Cache result
                # 4. Return name
                ...
    """

    async def resolve_user(self, user_id: str) -> str | None:
        """Resolve single user ID to display name.

        Args:
            user_id: Platform-specific user ID (e.g., Slack U123, Feishu ou_abc)

        Returns:
            Display name if found, None if not found or API failed.
            Implementation should use internal cache for performance.
        """
        ...

    async def resolve_batch(
        self,
        user_ids: list[str],
        max_concurrent: int = 4,
    ) -> dict[str, str | None]:
        """Resolve multiple user IDs concurrently.

        Args:
            user_ids: List of user IDs to resolve
            max_concurrent: Maximum concurrent API calls (default: 4)

        Returns:
            Dict mapping user_id -> display_name (None if not found)

        Note:
            Default implementation uses resolve_user() with asyncio.gather.
            Subclasses can override for platform-specific batch APIs.
        """
        ...


class UserResolverCache:
    """LRU cache with TTL, negative result caching, and eviction callback.

    Thread-safe cache for user ID -> display name mappings.
    Supports TTL-based expiration and LRU eviction when max_size exceeded.
    Negative results (None) are also cached to prevent repeated API failures.
    Optional eviction callback for metrics/monitoring (invoked on LRU eviction).

    Usage:
        # Basic usage
        cache = UserResolverCache(ttl_seconds=3600, max_size=1000)

        # With eviction callback for metrics
        cache = UserResolverCache(
            ttl_seconds=3600,
            max_size=1000,
            eviction_callback=lambda: metrics_counter.add(1),
        )

        # Get (returns sentinel object() for cache miss)
        result = await cache.get("U123")
        if result is None:
            # Cached negative result
            return None
        if isinstance(result, str):
            # Cache hit
            return result
        # Cache miss (sentinel object)
        name = await api_call()
        await cache.set("U123", name)

    Attributes:
        ttl_seconds: Time-to-live for cache entries (default: 3600 = 1 hour)
        max_size: Maximum cache size before LRU eviction (default: 1000)
        eviction_callback: Optional callback invoked on LRU eviction (for metrics)

    Note:
        Eviction callback exceptions are caught and logged, ensuring cache
        operations continue normally even if callback fails.
    """

    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_size: int = 1000,
        eviction_callback: Callable[[], None] | None = None,
    ) -> None:
        """Initialize cache with TTL and max size.

        Args:
            ttl_seconds: Cache entry TTL in seconds (default: 3600 = 1 hour)
            max_size: Maximum cache size (default: 1000 entries)
            eviction_callback: Optional callback invoked on LRU eviction
        """
        self._cache: dict[str, tuple[str | None, float]] = {}
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._eviction_callback = eviction_callback

    async def get(self, key: str) -> str | None | object:
        """Get cached value with TTL check.

        Args:
            key: Cache key (user_id)

        Returns:
            - str: Cached display name (valid)
            - None: Cached negative result (API returned None)
            - object(): Sentinel for cache miss (not cached or expired)

        Note:
            Use isinstance() to distinguish between cached None and miss:
                result = await cache.get(key)
                if result is None:
                    return None  # Cached negative result
                if isinstance(result, str):
                    return result  # Cache hit
                # Cache miss (sentinel)
        """
        async with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                return object()  # Cache miss

            value, cache_time = cached
            if time.time() - cache_time >= self._ttl:
                # Expired, remove and return miss
                self._cache.pop(key, None)
                return object()

            # Valid cache hit (value may be None for negative result)
            return value

    async def set(self, key: str, value: str | None) -> None:
        """Set cache entry with current timestamp.

        Args:
            key: Cache key (user_id)
            value: Display name (str) or None (negative result)

        Note:
            Supports negative result caching (value=None) to prevent
            repeated API calls for non-existent users or API failures.
        """
        async with self._lock:
            # Evict LRU if at capacity
            if len(self._cache) >= self._max_size and key not in self._cache:
                await self._evict_lru()

            self._cache[key] = (value, time.time())

    async def _evict_lru(self) -> None:
        """Evict oldest (least recently used) entry.

        Note:
            Called internally when cache reaches max_size.
            Evicts entry with oldest timestamp.
            Invokes eviction_callback if provided (exceptions are caught and logged).
        """
        if not self._cache:
            return

        # Find oldest entry by timestamp
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
        self._cache.pop(oldest_key, None)

        # Invoke callback for metrics/monitoring
        if self._eviction_callback:
            try:
                self._eviction_callback()
            except Exception as e:
                logger.warning("Eviction callback failed: %s", e, exc_info=True)

    async def clear(self) -> None:
        """Clear all cache entries.

        Note:
            Useful for testing or when credential/workspace changes.
        """
        async with self._lock:
            self._cache.clear()

    def get_stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dict with keys: size, max_size, ttl_seconds

        Note:
            Useful for monitoring and debugging.
        """
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl,
        }
