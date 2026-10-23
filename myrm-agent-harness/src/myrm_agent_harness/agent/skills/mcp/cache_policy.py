"""Session-scoped result-cache policy for PTC MCP calls.

[INPUT]
- backends.skills.types::SkillMetadata (POS: serialized MCP server config)
- utils.lru_cache::LRUCache (POS: bounded TTL cache)

[OUTPUT]
- DEFAULT_CACHE_TTL_SECONDS: default cache-bucket lifetime
- resolve_cache_ttl(): per-server TTL/allowlist policy
- is_explicitly_cacheable(): short/prefixed/hyphen name matching for allowlists
- CacheBuckets: fixed-TTL LRU buckets keyed by resolved TTL, with write invalidation
- get_cache_buckets(): process-wide cache shared by PTC and Direct FC

[POS]
Pure MCP result-cache policy shared by PTC proxy calls and Direct FC tools. Kept
out of proxy_service so each caller only asks "may this tool be cached, and for
how long?".
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.mcp.tool_name_utils import mcp_tool_short_name
from myrm_agent_harness.utils.lru_cache import LRUCache

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.types import SkillMetadata

DEFAULT_CACHE_TTL_SECONDS = 60
"""Default cache bucket lifetime used when an explicit config omits a TTL.

Caching itself is opt-in via ``cache_ttl_seconds`` plus ``cacheable_tools``;
there is no implicit readOnlyHint cache. The short bucket keeps repeated
identical lookups inside one script from accumulating stale state.
"""


def server_cache_config(skill_meta: SkillMetadata | None) -> dict[str, object]:
    """Read the first serialized MCP config entry, if present."""
    if skill_meta is None or skill_meta.mcp is None:
        return {}
    configs = skill_meta.mcp.config
    if isinstance(configs, list) and configs and isinstance(configs[0], dict):
        return configs[0]
    return {}


def cache_config_from_values(
    cache_ttl_seconds: object,
    cacheable_tools: object,
) -> dict[str, object]:
    """Build the tiny policy mapping used by both skill and direct tool callers."""
    return {"cache_ttl_seconds": cache_ttl_seconds, "cacheable_tools": cacheable_tools}


def make_cache_key(session_id: str, server_name: str, tool_name: str, params: object) -> str:
    """Build an opaque cache key isolated by session, server, tool, and arguments."""
    payload = json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
    params_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{session_id}.{server_name}.{tool_name}:{params_hash}"


def _cache_name_aliases(name: str) -> set[str]:
    """Return normalized aliases for a configured or canonical MCP tool name.

    Users copy names from ``tools/list`` (``get-tickets``), while the runtime
    catalog uses ``mcp__server__get-tickets``. Python callers may also use the
    underscored form. Treat all three as the same tool for allowlist matching;
    otherwise a valid configuration silently never caches.
    """
    aliases = {name, mcp_tool_short_name(name)}
    return {alias.replace("-", "_") for alias in aliases if alias}


def is_explicitly_cacheable_config(config: dict[str, object], tool_name: str) -> bool:
    """Return True when a policy mapping allowlists *tool_name* in any form."""
    cacheable = config.get("cacheable_tools")
    if not isinstance(cacheable, list):
        return False
    wanted = _cache_name_aliases(tool_name)
    return any(
        isinstance(entry, str) and bool(wanted & _cache_name_aliases(entry.strip()))
        for entry in cacheable
    )


def is_explicitly_cacheable(skill_meta: SkillMetadata | None, tool_name: str) -> bool:
    """Return True when a skill's serialized config allowlists *tool_name*."""
    return is_explicitly_cacheable_config(server_cache_config(skill_meta), tool_name)


def resolve_cache_ttl(skill_meta: SkillMetadata | None, tool_name: str) -> int | None:
    """Resolve the explicit cache TTL for one canonical tool, or ``None``.

    Caching is user-configured only: a positive ``cache_ttl_seconds`` plus the
    tool appearing in ``cacheable_tools``. There is no implicit readOnlyHint
    fallback, so the effective behavior always matches the visible config.
    """
    return resolve_cache_ttl_from_config(server_cache_config(skill_meta), tool_name)


def resolve_cache_ttl_from_config(config: dict[str, object], tool_name: str) -> int | None:
    """Resolve TTL from a policy mapping shared by PTC and Direct FC callers."""
    raw_ttl = config.get("cache_ttl_seconds")
    if raw_ttl is None:
        return None
    try:
        ttl = int(raw_ttl)
    except (TypeError, ValueError):
        return None
    if ttl <= 0 or not is_explicitly_cacheable_config(config, tool_name):
        return None
    return ttl


class CacheBuckets:
    """Fixed-TTL LRU caches keyed by the resolved per-server TTL."""

    def __init__(self, default_ttl: int = DEFAULT_CACHE_TTL_SECONDS) -> None:
        self.default = LRUCache[object](maxsize=1000, ttl=default_ttl, id="mcp_skill_readonly_cache")
        self._buckets: dict[int, LRUCache[object]] = {}

    def clear(self) -> None:
        """Drop every cached result after a write changes server state."""
        self.default.clear()
        for bucket in self._buckets.values():
            bucket.clear()

    def get(self, ttl: int) -> LRUCache[object]:
        """Return the cache bucket for *ttl*, creating it on first use."""
        if ttl == self.default.ttl:
            return self.default
        bucket = self._buckets.get(ttl)
        if bucket is None:
            bucket = LRUCache(maxsize=1000, ttl=ttl, id=f"mcp_skill_readonly_cache_{ttl}s")
            self._buckets[ttl] = bucket
        return bucket


_SHARED_CACHE = CacheBuckets()


def get_cache_buckets() -> CacheBuckets:
    """Return the process-wide MCP result cache shared by PTC and Direct FC."""
    return _SHARED_CACHE
