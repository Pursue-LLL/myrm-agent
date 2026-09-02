"""Feishu user resolver implementation using contact API.

[INPUT]
- channels.core.user_resolver::UserResolverCache (POS: Generic user resolver protocol and cache implementation. Protocol-first framework design supporting Slack/Feishu/Discord platform extensions with unified username resolution and caching.)
- channels.providers.feishu.sdk::FeishuClient (POS: Standalone Feishu OpenAPI client.)

[OUTPUT]
- FeishuUserResolver: Feishu-specific user resolver with LRU+TTL caching

[POS]
Feishu user resolver. Calls contact API to fetch user display name.
Supports single and batch resolution with built-in LRU+TTL cache and negative result caching.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.tracing import get_meter

from app.channels.core.user_resolver import UserResolverCache
from app.channels.providers.feishu.contact_fuzzy import (
    ContactCandidate,
    ContactMatchResult,
    FeishuContactFuzzyMatcher,
)

if TYPE_CHECKING:
    from app.channels.providers.feishu.sdk import FeishuClient

logger = logging.getLogger(__name__)


class FeishuUserResolver:
    """Feishu user resolver using contact API with caching.

    Implements UserResolver protocol for Feishu platform.
    Uses LRU+TTL cache to minimize API calls and supports negative caching
    to prevent repeated failures.

    Usage:
        resolver = FeishuUserResolver(feishu_client, cache_ttl=3600)
        name = await resolver.resolve_user("ou_abc")
        names = await resolver.resolve_batch(["ou_abc", "ou_def"], max_concurrent=4)

    Attributes:
        cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
        cache_max_size: Maximum cache entries (default: 1000)
    """

    def __init__(
        self,
        api_client: FeishuClient,
        *,
        cache_ttl: int = 3600,
        cache_max_size: int = 1000,
    ) -> None:
        """Initialize Feishu user resolver.

        Args:
            api_client: FeishuClient instance for API calls
            cache_ttl: Cache TTL in seconds (default: 3600)
            cache_max_size: Maximum cache entries (default: 1000)
        """
        self._api = api_client

        # OpenTelemetry metrics for observability
        meter = get_meter(__name__)
        self._cache_hit_counter = meter.create_counter(
            "feishu_user_resolver_cache_hits",
            description="Number of cache hits for user resolver",
        )
        self._cache_miss_counter = meter.create_counter(
            "feishu_user_resolver_cache_misses",
            description="Number of cache misses for user resolver",
        )
        self._cache_eviction_counter = meter.create_counter(
            "feishu_user_resolver_cache_evictions",
            description="Number of cache evictions (LRU)",
        )
        self._api_call_counter = meter.create_counter(
            "feishu_user_resolver_api_calls",
            description="Number of Feishu contact API calls",
        )
        self._api_failure_counter = meter.create_counter(
            "feishu_user_resolver_api_failures",
            description="Number of failed Feishu contact API calls",
        )

        # Initialize cache with eviction callback
        self._cache = UserResolverCache(
            ttl_seconds=cache_ttl,
            max_size=cache_max_size,
            eviction_callback=lambda: self._cache_eviction_counter.add(1),
        )

    async def resolve_user(self, user_id: str) -> str | None:
        """Resolve Feishu user ID to display name.

        Args:
            user_id: Feishu user ID (e.g., ou_abc)

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
            user_info = await self._api.get_user(user_id)
            if not user_info:
                await self._cache.set(user_id, None)
                return None

            # 3. Extract name (prefer name > en_name)
            name = user_info.get("name")
            if name and isinstance(name, str):
                name = name.strip()
                if name:
                    await self._cache.set(user_id, name)
                    return name

            en_name = user_info.get("en_name")
            if en_name and isinstance(en_name, str):
                en_name = en_name.strip()
                if en_name:
                    await self._cache.set(user_id, en_name)
                    return en_name

            # No valid name found
            await self._cache.set(user_id, None)
            return None

        except Exception as exc:
            logger.debug("Failed to resolve Feishu user %s: %s", user_id, exc)
            self._api_failure_counter.add(1)
            # Cache negative result to prevent retry storm
            await self._cache.set(user_id, None)
            return None

    async def resolve_batch(
        self,
        user_ids: list[str],
        max_concurrent: int = 4,
    ) -> dict[str, str | None]:
        """Resolve multiple Feishu user IDs concurrently.

        Args:
            user_ids: List of Feishu user IDs
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

    async def search_contact_fuzzy(
        self,
        query: str,
        *,
        limit: int = 5,
        department_hint: str = "",
    ) -> ContactMatchResult:
        """Search contacts by name or pinyin with phonetic tolerance and disambiguation.

        Fetches department users (cached) and executes fuzzy scoring.
        """
        if not query.strip():
            return ContactMatchResult(query=query)

        # Fetch department users from Feishu API
        try:
            users, _ = await self._api.list_users(department_id="0", page_size=50)
        except Exception as exc:
            logger.debug("Failed to list Feishu users for fuzzy matching: %s", exc)
            users = []

        matcher = FeishuContactFuzzyMatcher(users)
        return matcher.match(query, limit=limit, department_hint=department_hint)
