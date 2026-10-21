"""通道功能 Mixin - 可复用 通道能力Component

provides可组合 通道功能Module，如群组Cache、消息队列 etc.。

[INPUT]
- channels.types::GroupInfo (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.core.events::EventEmitter (POS: Channel event infrastructure. Channels emit events (status changes, group updates), Gateway or other components subscribe. Provides better extensibility and decoupling than traditional callback patterns.)

[OUTPUT]
- EventEmitterProtocol: EventEmitter Type约束
- CachedGroupMixin: 群组ListCache Mixin（Support TTL  and 变化检测）

[POS]
Reusable channel capability components via Mixin pattern. Allows different channels
to share functionality (caching, rate limiting, retry, etc.) without code duplication.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.channels.types import GroupInfo

logger = logging.getLogger(__name__)


class EventEmitterProtocol(Protocol):
    """EventEmitter Type约束 -  for  Mixin TypeSecurity"""

    _name: str

    def emit(self, event_type: str, data: object = None) -> None:
        """Emit an event to all registered listeners."""
        ...


class CachedGroupMixin:
    """群组ListCache Mixin

     is 通道provides群组List Cache能力，Support：
    - TTL Auto失效（Default 5 分钟）
    - 变化检测（基于 JID 集合比较）
    -  via  EventEmitter Auto发布 groups_change 事件

     using 方式：
        class MyChannel(BaseChannel, CachedGroupMixin):
            def __init__(self, ...):
                BaseChannel.__init__(self)
                CachedGroupMixin.__init__(self, groups_cache_ttl=300.0)

            async def list_groups(self, force_refresh: bool = False):
                if self._is_groups_cache_valid(force_refresh):
                    return self._groups_cache.copy()

                fresh_groups = await self._fetch_from_remote()
                self._update_groups_cache(fresh_groups)
                return fresh_groups
    """

    def __init__(self, groups_cache_ttl: float = 300.0) -> None:
        """Initialize groups cache.

        Args:
            groups_cache_ttl: Cache TTL in seconds (default 5 minutes).
        """
        self._groups_cache: list[GroupInfo] = []
        self._groups_cache_time: float = 0.0
        self._groups_cache_ttl: float = groups_cache_ttl

    def _is_groups_cache_valid(self, force_refresh: bool) -> bool:
        """Check if groups cache is valid.

        Args:
            force_refresh: If True, cache is considered invalid.

        Returns:
            True if cache is valid and can be used.
        """
        if not self._groups_cache or force_refresh:
            return False

        now = time.time()
        return (now - self._groups_cache_time) < self._groups_cache_ttl

    def _update_groups_cache(self: EventEmitterProtocol, groups: list[GroupInfo]) -> None:
        """Update groups cache and emit event if changed.

        Args:
            groups: New groups list.
        """
        if not groups:
            if self._groups_cache:
                self._groups_cache = []
                self._groups_cache_time = time.time()
                self.emit("groups_change", [])
                logger.info("%s: groups cleared", self._name)
            return

        old_jids = {g.jid for g in self._groups_cache}
        new_jids = {g.jid for g in groups}
        cache_changed = old_jids != new_jids

        if cache_changed:
            self._groups_cache = groups
            self._groups_cache_time = time.time()
            self.emit("groups_change", groups)
            logger.info("%s: groups updated (%d groups)", self._name, len(groups))
        else:
            self._groups_cache = groups
            self._groups_cache_time = time.time()

    def _get_groups_cache_metrics(self) -> dict[str, object]:
        """Get cache metrics for monitoring.

        Returns:
            Dict with cache_size, cache_age, ttl_remaining.
        """
        now = time.time()
        cache_age = now - self._groups_cache_time if self._groups_cache_time > 0 else 0
        ttl_remaining = max(0, self._groups_cache_ttl - cache_age)

        return {
            "cache_size": len(self._groups_cache),
            "cache_age_seconds": cache_age,
            "ttl_remaining_seconds": ttl_remaining,
            "is_valid": self._is_groups_cache_valid(force_refresh=False),
        }
