"""LINE user resolver implementation using LINE profile APIs.

[INPUT]
- channels.core.user_resolver::UserResolverCache (POS: Generic user resolver protocol and cache implementation. Protocol-first framework design supporting Slack/Feishu/Discord platform extensions with unified username resolution and caching.)
- channels.providers.line.api::LineClient (POS: LINE HTTP layer. Called by channel.py via self._api.)

[OUTPUT]
- LINEUserResolver: LINE-specific user resolver with LRU+TTL caching

[POS]
LINE user resolver. Resolves user display names via 1:1 / group / room
profile APIs (Get Profile / Get Group Member Profile / Get Room Member
Profile), selecting the endpoint by chat scope. Built-in LRU+TTL cache with
negative-result caching and scope-aware cache keys.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal

from myrm_agent_harness.infra.tracing import get_meter

from app.channels.core.user_resolver import UserResolverCache

if TYPE_CHECKING:
    from app.channels.providers.line.api import LineClient

logger = logging.getLogger(__name__)

LineChatScope = Literal["user", "group", "room"]


class LINEUserResolver:
    """LINE user resolver using scope-aware profile APIs with caching.

    Implements UserResolver protocol for LINE platform. Because LINE's
    Get Profile API only works for 1:1 friends while group/room members may
    not be friends, resolution must select the correct endpoint by scope:

    - ``user``  : GET /v2/bot/profile/{userId}          (get_user_profile)
    - ``group`` : GET /v2/bot/group/{groupId}/member/{userId} (get_group_member_profile)
    - ``room``  : GET /v2/bot/room/{roomId}/member/{userId}   (get_room_member_profile)

    Cache keys are scope-aware (scope + chat_id + user_id) so the same user
    resolved in different chats is cached independently. Uses LRU+TTL cache
    with negative-result caching to prevent repeated failures.

    Usage:
        resolver = LINEUserResolver(line_client, cache_ttl=3600)
        name = await resolver.resolve_user("U12345")                      # 1:1
        name = await resolver.resolve_user("U12345", scope="group", chat_id="C1")
        name = await resolver.resolve_user("U12345", scope="room", chat_id="R1")

    Attributes:
        cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
        cache_max_size: Maximum cache entries (default: 1000)
    """

    def __init__(
        self,
        api_client: LineClient,
        *,
        cache_ttl: int = 3600,
        cache_max_size: int = 1000,
    ) -> None:
        """Initialize LINE user resolver.

        Args:
            api_client: LineClient instance for API calls
            cache_ttl: Cache TTL in seconds (default: 3600)
            cache_max_size: Maximum cache entries (default: 1000)
        """
        self._api = api_client

        meter = get_meter(__name__)
        self._cache_hit_counter = meter.create_counter(
            "line_user_resolver_cache_hits",
            description="Number of cache hits for user resolver",
        )
        self._cache_miss_counter = meter.create_counter(
            "line_user_resolver_cache_misses",
            description="Number of cache misses for user resolver",
        )
        self._cache_eviction_counter = meter.create_counter(
            "line_user_resolver_cache_evictions",
            description="Number of cache evictions (LRU)",
        )
        self._api_call_counter = meter.create_counter(
            "line_user_resolver_api_calls",
            description="Number of LINE profile API calls",
        )
        self._api_failure_counter = meter.create_counter(
            "line_user_resolver_api_failures",
            description="Number of failed LINE profile API calls",
        )

        self._cache = UserResolverCache(
            ttl_seconds=cache_ttl,
            max_size=cache_max_size,
            eviction_callback=lambda: self._cache_eviction_counter.add(1),
        )

    async def resolve_user(
        self,
        user_id: str,
        *,
        scope: LineChatScope = "user",
        chat_id: str = "",
    ) -> str | None:
        """Resolve a LINE user's display name.

        Args:
            user_id: LINE user ID (e.g., U12345).
            scope: Chat scope: ``user`` (1:1), ``group``, or ``room``.
            chat_id: Group/room ID; required when scope is ``group``/``room``.

        Returns:
            Display name if found, else None (not found or API failed).
            Checks cache first, falls back to the scope-appropriate profile API.
        """
        if not user_id:
            return None

        cache_key = self._cache_key(scope, chat_id, user_id)

        cached = await self._cache.get(cache_key)
        if cached is None:
            self._cache_hit_counter.add(1)
            return None
        if isinstance(cached, str):
            self._cache_hit_counter.add(1)
            return cached

        self._cache_miss_counter.add(1)
        self._api_call_counter.add(1)
        try:
            profile = await self._fetch_profile(scope, chat_id, user_id)
            name = self._extract_name(profile)
            await self._cache.set(cache_key, name)
            return name
        except Exception as exc:
            logger.debug("Failed to resolve LINE user %s in scope %s: %s", user_id, scope, exc)
            self._api_failure_counter.add(1)
            await self._cache.set(cache_key, None)
            return None

    async def resolve_batch(
        self,
        user_ids: list[str],
        *,
        max_concurrent: int = 4,
        scope: LineChatScope = "user",
        chat_id: str = "",
    ) -> dict[str, str | None]:
        """Resolve multiple LINE user IDs concurrently in one chat scope.

        Args:
            user_ids: List of LINE user IDs.
            max_concurrent: Maximum concurrent API calls (default: 4).
            scope: Chat scope for all IDs (``user``/``group``/``room``).
            chat_id: Group/room ID; required for ``group``/``room`` scopes.

        Returns:
            Dict mapping user_id -> display_name (None if not found).
        """
        if not user_ids:
            return {}

        unique_ids = list(dict.fromkeys(user_ids))
        semaphore = asyncio.Semaphore(max_concurrent)

        async def resolve_one(uid: str) -> tuple[str, str | None]:
            async with semaphore:
                name = await self.resolve_user(uid, scope=scope, chat_id=chat_id)
                return uid, name

        tasks = [resolve_one(uid) for uid in unique_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        result_dict: dict[str, str | None] = {}
        for res in results:
            if isinstance(res, tuple) and len(res) == 2:
                uid, name = res
                result_dict[uid] = name
            elif isinstance(res, Exception):
                logger.debug("Batch resolve exception: %s", res)
        return result_dict

    @staticmethod
    def _cache_key(scope: LineChatScope, chat_id: str, user_id: str) -> str:
        """Build a scope-aware cache key so the same user in different chats
        is resolved independently (their display name may differ per chat)."""
        return f"{scope}:{chat_id}:{user_id}"

    async def _fetch_profile(
        self,
        scope: LineChatScope,
        chat_id: str,
        user_id: str,
    ) -> dict[str, str]:
        """Fetch the profile for a user in the given chat scope."""
        if scope == "group":
            return await self._api.get_group_member_profile(chat_id, user_id)
        if scope == "room":
            return await self._api.get_room_member_profile(chat_id, user_id)
        return await self._api.get_user_profile(user_id)

    @staticmethod
    def _extract_name(profile: dict[str, str]) -> str | None:
        """Extract a non-blank display name from a profile dict."""
        display_name = profile.get("displayName")
        if display_name and isinstance(display_name, str):
            name = display_name.strip()
            if name:
                return name
        return None
