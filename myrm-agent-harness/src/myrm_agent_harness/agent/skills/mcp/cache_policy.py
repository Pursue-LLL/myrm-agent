"""Session-scoped result-cache policy for PTC MCP calls.

[INPUT]
- backends.skills.types::SkillMetadata (POS: serialized MCP server config)
- utils.lru_cache::LRUCache (POS: bounded TTL cache)

[OUTPUT]
- READ_ONLY_CACHE_TTL_SECONDS: default read-only cache lifetime
- resolve_cache_ttl(): per-server TTL/allowlist policy
- CacheBuckets: fixed-TTL LRU buckets keyed by resolved TTL

[POS]
Pure cache policy for the MCP skill proxy. Kept out of proxy_service so the
invoke path only asks "may this tool be cached, and for how long?".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.utils.lru_cache import LRUCache

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.types import SkillMetadata

READ_ONLY_CACHE_TTL_SECONDS = 60
"""Default session-scoped cache lifetime for readOnlyHint tools.

Short by design: the cache absorbs repeated identical lookups inside one script,
not across a conversation. A longer TTL makes status polling return stale data.
Mutating tools never enter this cache.
"""


def server_cache_config(skill_meta: SkillMetadata | None) -> dict[str, object]:
    """Read the first serialized MCP config entry, if present."""
    if skill_meta is None or skill_meta.mcp is None:
        return {}
    configs = skill_meta.mcp.config
    if isinstance(configs, list) and configs and isinstance(configs[0], dict):
        return configs[0]
    return {}


def resolve_cache_ttl(
    skill_meta: SkillMetadata | None,
    tool_name: str,
    *,
    is_read_only: bool,
) -> int | None:
    """Resolve the cache TTL for one canonical tool, or ``None`` when uncached.

    Read-only tools inherit the default TTL. Servers may explicitly allowlist
    stable tools that omit ``readOnlyHint``; they may also set
    ``cache_ttl_seconds`` to zero to disable caching or a positive value to cap
    the lifetime. Dynamic ticket/status tools must never be allowlisted.
    """
    config = server_cache_config(skill_meta)
    cacheable = config.get("cacheable_tools")
    explicit = isinstance(cacheable, list) and tool_name in cacheable
    if not is_read_only and not explicit:
        return None

    raw_ttl = config.get("cache_ttl_seconds")
    if raw_ttl is None:
        return READ_ONLY_CACHE_TTL_SECONDS
    try:
        ttl = int(raw_ttl)
    except (TypeError, ValueError):
        return READ_ONLY_CACHE_TTL_SECONDS
    return ttl if ttl > 0 else None


class CacheBuckets:
    """Fixed-TTL LRU caches keyed by the resolved per-server TTL."""

    def __init__(self, default_ttl: int = READ_ONLY_CACHE_TTL_SECONDS) -> None:
        self.default = LRUCache[object](maxsize=1000, ttl=default_ttl, id="mcp_skill_readonly_cache")
        self._buckets: dict[int, LRUCache[object]] = {}

    def get(self, ttl: int) -> LRUCache[object]:
        """Return the cache bucket for *ttl*, creating it on first use."""
        if ttl == self.default.ttl:
            return self.default
        bucket = self._buckets.get(ttl)
        if bucket is None:
            bucket = LRUCache(maxsize=1000, ttl=ttl, id=f"mcp_skill_readonly_cache_{ttl}s")
            self._buckets[ttl] = bucket
        return bucket
