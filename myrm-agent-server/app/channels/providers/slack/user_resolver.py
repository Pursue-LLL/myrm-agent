"""Slack user resolver implementation using users.info API.

[INPUT]
- channels.core.user_resolver::UserResolver, (POS: Generic user resolver protocol and cache implementation. Protocol-first framework design supporting Slack/Feishu/Discord platform extensions with unified username resolution and caching.)
- channels.providers.slack.api::SlackClient (POS: DingTalk OpenAPI client. Encapsulates token management, message sending (DM/group), media upload/download for DingTalkChannel.)

[OUTPUT]
- SlackUserResolver: Slack-specific user resolver with LRU+TTL caching

[POS]
Slack user resolver. Calls users.info API to fetch display_name/real_name.
Supports single and batch resolution with built-in LRU+TTL cache and negative result caching.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.tracing import get_meter

from app.channels.core.user_resolver import UserResolverCache

if TYPE_CHECKING:
    from app.channels.providers.slack.api import SlackClient

logger = logging.getLogger(__name__)


class SlackUserResolver:
    """Slack user resolver using users.info API with caching.

    Implements UserResolver protocol for Slack platform.
    Uses LRU+TTL cache to minimize API calls and supports negative caching
    to prevent repeated failures.

    Usage:
        resolver = SlackUserResolver(slack_client, cache_ttl=3600)
        name = await resolver.resolve_user("U12345")
        names = await resolver.resolve_batch(["U123", "U456"], max_concurrent=4)

    Attributes:
        cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
        cache_max_size: Maximum cache entries (default: 1000)
    """

    def __init__(
        self,
        api_client: SlackClient,
        *,
        cache_ttl: int = 3600,
        cache_max_size: int = 1000,
    ) -> None:
        """Initialize Slack user resolver.

        Args:
            api_client: SlackClient instance for API calls
            cache_ttl: Cache TTL in seconds (default: 3600)
            cache_max_size: Maximum cache entries (default: 1000)
        """
        self._api = api_client

        # OpenTelemetry metrics for observability
        meter = get_meter(__name__)
        self._cache_hit_counter = meter.create_counter(
            "slack_user_resolver_cache_hits",
            description="Number of cache hits for user resolver",
        )
        self._cache_miss_counter = meter.create_counter(
            "slack_user_resolver_cache_misses",
            description="Number of cache misses for user resolver",
        )
        self._cache_eviction_counter = meter.create_counter(
            "slack_user_resolver_cache_evictions",
            description="Number of cache evictions (LRU)",
        )
        self._api_call_counter = meter.create_counter(
            "slack_user_resolver_api_calls",
            description="Number of Slack users.info API calls",
        )
        self._api_failure_counter = meter.create_counter(
            "slack_user_resolver_api_failures",
            description="Number of failed Slack users.info API calls",
        )

        # Initialize cache with eviction callback
        self._cache = UserResolverCache(
            ttl_seconds=cache_ttl,
            max_size=cache_max_size,
            eviction_callback=lambda: self._cache_eviction_counter.add(1),
        )

    async def resolve_user(self, user_id: str) -> str | None:
        """Resolve Slack user ID to display name.

        Args:
            user_id: Slack user ID (e.g., U12345)

        Returns:
            Display name if found, None if not found or API failed.
            Checks cache first, falls back to users.info API.

        Note:
            - Prefers display_name > real_name > name
            - Caches both positive and negative results
            - API failures are cached as None to prevent retry storms
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
            user_info = await self._api.users_info(user_id)
            if not user_info:
                await self._cache.set(user_id, None)
                return None

            # 3. Extract name (prefer display_name > real_name > name)
            profile = user_info.get("profile", {})
            if isinstance(profile, dict):
                display_name = profile.get("display_name")
                if display_name and isinstance(display_name, str):
                    name = display_name.strip()
                    if name:
                        await self._cache.set(user_id, name)
                        return name

                real_name = profile.get("real_name")
                if real_name and isinstance(real_name, str):
                    name = real_name.strip()
                    if name:
                        await self._cache.set(user_id, name)
                        return name

            fallback_name = user_info.get("name")
            if fallback_name and isinstance(fallback_name, str):
                name = fallback_name.strip()
                if name:
                    await self._cache.set(user_id, name)
                    return name

            # No valid name found
            await self._cache.set(user_id, None)
            return None

        except Exception as exc:
            logger.debug("Failed to resolve Slack user %s: %s", user_id, exc)
            self._api_failure_counter.add(1)
            # Cache negative result to prevent retry storm
            await self._cache.set(user_id, None)
            return None

    async def resolve_batch(
        self,
        user_ids: list[str],
        max_concurrent: int = 4,
    ) -> dict[str, str | None]:
        """Resolve multiple Slack user IDs concurrently.

        Args:
            user_ids: List of Slack user IDs
            max_concurrent: Maximum concurrent API calls (default: 4)

        Returns:
            Dict mapping user_id -> display_name (None if not found)

        Note:
            - Deduplicates input user_ids
            - Uses semaphore to limit concurrent API calls
            - Leverages cache for performance
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
