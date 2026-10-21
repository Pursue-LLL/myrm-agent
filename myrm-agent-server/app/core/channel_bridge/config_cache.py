"""Config cache with TTL eviction.

Provides in-memory cache for user configs with 30s TTL.

[INPUT]
- configs: UserConfigs

[OUTPUT]
- _get_cached: retrieve cached configs if valid
- _set_cached: store configs with timestamp
- invalidate_user_configs_cache: force invalidation after updates
- schedule_memory_manager_config_invalidation: sync invalidation (dedup cache only; prefer await_memory_manager_config_invalidation)
- await_memory_manager_config_invalidation: await MemoryManager shutdown after providers config changes

[POS]
Business-layer config caching. Simple dict + timestamp implementation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

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


def _invalidate_platform_dedup_llm_cache_sync() -> None:
    try:
        from app.services.memory.extract_retry.resolve_chat_extraction_llm import (
            invalidate_platform_dedup_llm_cache,
        )

        invalidate_platform_dedup_llm_cache()
    except Exception:
        logger.warning("Failed to invalidate platform dedup LLM cache (non-fatal)", exc_info=True)


async def await_memory_manager_config_invalidation() -> None:
    """Evict MemoryManager cache when provider/lite model config may have changed."""
    _invalidate_platform_dedup_llm_cache_sync()
    from app.core.memory.adapters.setup import shutdown_cached_memory_managers

    await shutdown_cached_memory_managers()


def schedule_memory_manager_config_invalidation() -> None:
    """Best-effort async invalidation when no event loop caller can await."""
    _invalidate_platform_dedup_llm_cache_sync()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    from app.core.memory.adapters.setup import shutdown_cached_memory_managers

    loop.create_task(shutdown_cached_memory_managers())


def invalidate_user_configs_cache() -> None:
    """Invalidate cached configs for a user after config update/delete.

    Call this when config_service.set() or config_service.delete() succeeds
    to ensure load_user_configs() returns fresh data.
    Also cascades to agent readiness cache since readiness depends on user configs.
    """
    from app.core.infra.ingress import invalidate_public_ingress_cache

    _config_cache.pop("sandbox", None)
    invalidate_public_ingress_cache()

    try:
        from app.services.agent.readiness import get_readiness_resolver

        get_readiness_resolver().invalidate_all()
    except Exception:
        pass


__all__ = [
    "invalidate_user_configs_cache",
    "await_memory_manager_config_invalidation",
    "schedule_memory_manager_config_invalidation",
    "_get_cached",
    "_set_cached",
]
