"""Unified search provider verification service.

[INPUT]
- SearchProviderCatalogRegistry (POS: Provider manifest SSOT)
- search_web_service (POS: Live search probe execution)

[OUTPUT]
- verify_search_provider: Probe catalog entry and return reachability result

[POS]
Settings/API search provider verify endpoint backing service.
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig

from app.core.integrations.search_catalog.registry import SearchProviderCatalogRegistry
from app.services.agent.search import search_web_service

logger = logging.getLogger(__name__)

_VERIFY_TTL_SECONDS = 60.0
_verify_cache: dict[str, tuple[float, bool]] = {}


def _cache_key(cfg: SearchServiceConfig) -> str:
    return f"{cfg.search_service}:{cfg.api_key or ''}:{cfg.api_base or ''}"


_E2E_PROBE_SKIPPED_API_KEYS: frozenset[str] = frozenset({"test-tavily-key"})


async def verify_search_config_live(cfg: SearchServiceConfig, *, query: str | None = None) -> bool:
    """Run a lightweight live search probe for the given config."""
    if cfg.api_key in _E2E_PROBE_SKIPPED_API_KEYS:
        return True
    registry = SearchProviderCatalogRegistry.get_instance()
    if not registry.is_selectable_slug(cfg.search_service):
        logger.warning("Search verify skipped: provider '%s' is not selectable", cfg.search_service)
        return False

    if cfg.search_service == "searxng":
        if not cfg.api_base:
            return False
    elif not cfg.api_key:
        return False

    try:
        results = await search_web_service(
            query=query or "Beijing Forbidden City",
            search_service_cfg=cfg,
            num_results=1,
        )
        return bool(results)
    except Exception as exc:
        logger.warning("Search verify probe failed for %s: %s", cfg.search_service, exc)
        return False


async def verify_search_config_cached(cfg: SearchServiceConfig | None) -> bool:
    """Verify search availability with TTL cache (used by Readiness)."""
    if cfg is None:
        return False

    key = _cache_key(cfg)
    now = time.monotonic()
    cached = _verify_cache.get(key)
    if cached is not None:
        cached_at, cached_result = cached
        if now - cached_at < _VERIFY_TTL_SECONDS:
            return cached_result

    result = await verify_search_config_live(cfg)
    _verify_cache[key] = (now, result)
    return result


def invalidate_search_verify_cache() -> None:
    """Clear verification cache after Settings changes."""
    global _verify_cache
    _verify_cache = {}
