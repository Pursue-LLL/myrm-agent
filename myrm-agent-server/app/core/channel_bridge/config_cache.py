"""Config cache with TTL eviction.

Provides in-memory cache for user configs with 30s TTL.

[INPUT]
- configs: UserConfigs

[OUTPUT]
- _get_cached: retrieve cached configs if valid
- _set_cached: store configs with timestamp
- invalidate_user_configs_cache: force invalidation after updates

[POS]
Business-layer config caching. Simple dict + timestamp implementation.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.channel_bridge.config_loader import UserConfigs

_CONFIG_CACHE_TTL = 30  # seconds
_config_cache: dict[str, tuple[float, UserConfigs]] = {}


def _get_cached(sandbox: str) -> "UserConfigs | None":
    """Get cached configs if still valid, otherwise return None and evict."""
    entry = _config_cache.get(sandbox)
    if entry and (time.monotonic() - entry[0]) < _CONFIG_CACHE_TTL:
        return entry[1]
    _config_cache.pop(sandbox, None)
    return None


def _set_cached(sandbox: str, configs: "UserConfigs") -> None:
    """Store configs in cache with current timestamp."""
    _config_cache[sandbox] = (time.monotonic(), configs)
    if len(_config_cache) > 128:
        _evict_expired()


def _evict_expired() -> None:
    """Remove expired entries from cache."""
    now = time.monotonic()
    expired = [k for k, (ts, _) in _config_cache.items() if now - ts >= _CONFIG_CACHE_TTL]
    for k in expired:
        del _config_cache[k]


def invalidate_user_configs_cache() -> None:
    """Invalidate cached configs for a user after config update/delete.

    Call this when config_service.set() or config_service.delete() succeeds
    to ensure load_user_configs() returns fresh data.
    """
    from app.core.infra.ingress import invalidate_public_ingress_cache

    _config_cache.pop("sandbox", None)
    invalidate_public_ingress_cache()


__all__ = [
    "invalidate_user_configs_cache",
    "_get_cached",
    "_set_cached",
]
