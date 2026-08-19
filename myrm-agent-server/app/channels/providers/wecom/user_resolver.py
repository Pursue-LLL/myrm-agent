"""WeCom user resolver implementation using contact API.

[INPUT]
- channels.core.user_resolver::UserResolverCache (POS: Generic user resolver protocol and cache implementation. Protocol-first framework design supporting Slack/Feishu/Discord platform extensions with unified username resolution and caching.)
- channels.providers.wecom.channel::WeComChannel (POS: WeCom self-built app channel: AES encrypted callbacks, multimedia send/receive, @mention detection, OAuth token management.)

[OUTPUT]
- WeComUserResolver: WeCom-specific user resolver with LRU+TTL caching

[POS]
WeCom user resolver. Calls contact API to fetch user display name.
Supports single and batch resolution with built-in LRU+TTL cache and negative result caching.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.tracing import get_meter

from app.channels.core.user_resolver import UserResolverCache

if TYPE_CHECKING:
    from app.channels.providers.wecom.channel import WeComChannel

logger = logging.getLogger(__name__)


class WeComUserResolver:
    """WeCom user resolver using contact API with caching.

    Implements UserResolver protocol for WeCom platform.
    Uses LRU+TTL cache to minimize API calls and supports negative caching
    to prevent repeated failures.

    Usage:
        resolver = WeComUserResolver(wecom_channel, cache_ttl=3600)
        name = await resolver.resolve_user("zhangsan")
        names = await resolver.resolve_batch(["zhangsan", "lisi"], max_concurrent=4)

    Attributes:
        cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
        cache_max_size: Maximum cache entries (default: 1000)
    """

    def __init__(
        self,
        channel: WeComChannel,
        *,
        cache_ttl: int = 3600,
        cache_max_size: int = 1000,
    ) -> None:
        """Initialize WeCom user resolver.

        Args:
            channel: WeComChannel instance for token + HTTP access
            cache_ttl: Cache TTL in seconds (default: 3600)
            cache_max_size: Maximum cache entries (default: 1000)
        """
        self._channel = channel

        # OpenTelemetry metrics for observability
        meter = get_meter(__name__)
        self._cache_hit_counter = meter.create_counter(
            "wecom_user_resolver_cache_hits",
            description="Number of cache hits for user resolver",
        )
        self._cache_miss_counter = meter.create_counter(
            "wecom_user_resolver_cache_misses",
            description="Number of cache misses for user resolver",
        )
        self._cache_eviction_counter = meter.create_counter(
            "wecom_user_resolver_cache_evictions",
            description="Number of cache evictions (LRU)",
        )
        self._api_call_counter = meter.create_counter(
            "wecom_user_resolver_api_calls",
            description="Number of WeCom contact API calls",
        )
        self._api_failure_counter = meter.create_counter(
            "wecom_user_resolver_api_failures",
            description="Number of failed WeCom contact API calls",
        )

        # Initialize cache with eviction callback
        self._cache = UserResolverCache(
            ttl_seconds=cache_ttl,
            max_size=cache_max_size,
            eviction_callback=lambda: self._cache_eviction_counter.add(1),
        )

    async def resolve_user(self, user_id: str) -> str | None:
        """Resolve WeCom user ID to display name.

        Args:
            user_id: WeCom user ID (e.g., zhangsan)

        Returns:
            Display name if found, None if not found or API failed.
            Checks cache first, falls back to contact API.
        """
        if not user_id:
            return None

        # 1. Check cache
        cached = await self._cache.get(user_id)
        if cached is None:
            # Cached negative result
            self._cache_hit_counter.add(1)
            return None
        if isinstance(cached, str):
            # Cache hit
            self._cache_hit_counter.add(1)
            return cached

        # 2. Cache miss, call API
        self._cache_miss_counter.add(1)
        self._api_call_counter.add(1)
        try:
            user_info = await self._channel.api_get_user(user_id)
            if not user_info:
                await self._cache.set(user_id, None)
                return None

            # 3. Extract name (prefer name > alias)
            name = user_info.get("name")
            if name and isinstance(name, str):
                name = name.strip()
                if name:
                    await self._cache.set(user_id, name)
                    return name

            alias = user_info.get("alias")
            if alias and isinstance(alias, str):
                alias = alias.strip()
                if alias:
                    await self._cache.set(user_id, alias)
                    return alias

            # No valid name found
            await self._cache.set(user_id, None)
            return None

        except Exception as exc:
            logger.debug("Failed to resolve WeCom user %s: %s", user_id, exc)
            self._api_failure_counter.add(1)
            # Cache negative result to prevent retry storm
            await self._cache.set(user_id, None)
            return None

    async def resolve_batch(
        self,
        user_ids: list[str],
        max_concurrent: int = 4,
    ) -> dict[str, str | None]:
        """Resolve multiple WeCom user IDs concurrently.

        Args:
            user_ids: List of WeCom user IDs
            max_concurrent: Maximum concurrent API calls (default: 4)

        Returns:
            Dict mapping user_id -> display_name (None if not found)
        """
        if not user_ids:
            return {}

        # Deduplicate
        unique_ids = list(dict.fromkeys(user_ids))

        # Concurrent resolution with semaphore
        semaphore = asyncio.Semaphore(max_concurrent)

        async def resolve_one(uid: str) -> tuple[str, str | None]:
            async with semaphore:
                name = await self.resolve_user(uid)
                return uid, name

        tasks = [resolve_one(uid) for uid in unique_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dict, filter exceptions
        result_dict: dict[str, str | None] = {}
        for res in results:
            if isinstance(res, tuple) and len(res) == 2:
                uid, name = res
                result_dict[uid] = name
            elif isinstance(res, Exception):
                logger.debug("Batch resolve exception: %s", res)

        return result_dict
