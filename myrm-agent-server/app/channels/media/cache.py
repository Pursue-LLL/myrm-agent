"""Media download cache with LRU eviction.

[INPUT]
- (none)

[OUTPUT]
- CacheBackendProtocol: Protocol for cache backends.
- LRUMemoryCache: LRU (Least Recently Used) in-memory cache.
- url_to_cache_key: Convert URL to cache key using SHA256 hash.

[POS]
Media download cache with LRU eviction.
"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from typing import Protocol

logger = logging.getLogger(__name__)


class CacheBackendProtocol(Protocol):
    """Protocol for cache backends.

    Cache backends store downloaded media to avoid redundant downloads.
    """

    async def get(self, key: str) -> tuple[bytes, str] | None:
        """Get cached media data.

        Args:
            key: Cache key (typically URL hash).

        Returns:
            Tuple of (data, content_type) if cached, else None.
        """
        ...

    async def set(self, key: str, data: bytes, content_type: str, ttl_seconds: int = 3600) -> None:
        """Store media data in cache.

        Args:
            key: Cache key (typically URL hash).
            data: Media data bytes.
            content_type: Content-Type from response.
            ttl_seconds: Time-to-live in seconds. Default: 1 hour.
        """
        ...

    async def clear(self) -> None:
        """Clear all cached data."""
        ...


class LRUMemoryCache:
    """LRU (Least Recently Used) in-memory cache.

    This is a simple memory-based cache with LRU eviction policy.
    When max_size is reached, the least recently used item is evicted.

    Args:
        max_size: Maximum number of items to cache. Default: 100.
        max_item_bytes: Maximum size per item in bytes. Items larger than
            this are not cached. Default: 10MB.
    """

    def __init__(
        self,
        max_size: int = 100,
        max_item_bytes: int = 10 * 1024 * 1024,
    ):
        self.max_size = max_size
        self.max_item_bytes = max_item_bytes
        self._cache: OrderedDict[str, tuple[bytes, str]] = OrderedDict()

    async def get(self, key: str) -> tuple[bytes, str] | None:
        """Get cached data and move to end (most recently used)."""
        if key not in self._cache:
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return self._cache[key]

    async def set(self, key: str, data: bytes, content_type: str, ttl_seconds: int = 3600) -> None:
        """Store data in cache with LRU eviction."""
        # Skip if item is too large
        if len(data) > self.max_item_bytes:
            logger.debug(
                "Skipping cache: item size %d bytes exceeds max %d bytes",
                len(data),
                self.max_item_bytes,
            )
            return

        # Remove oldest item if at capacity
        if key not in self._cache and len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug("LRU eviction: removed key %s", oldest_key[:20])

        # Add or update item (moves to end)
        self._cache[key] = (data, content_type)
        self._cache.move_to_end(key)

    async def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()

    def __len__(self) -> int:
        """Return number of cached items."""
        return len(self._cache)


def url_to_cache_key(url: str) -> str:
    """Convert URL to cache key using SHA256 hash.

    Args:
        url: The URL to hash.

    Returns:
        Hex-encoded SHA256 hash of the URL.
    """
    return hashlib.sha256(url.encode()).hexdigest()
