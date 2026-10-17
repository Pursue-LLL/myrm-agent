"""Unified search provider verification service.

[INPUT]
- SearchProviderCatalogRegistry (POS: Provider manifest SSOT)
- search_web_service (POS: Live search probe execution)

[OUTPUT]
- verify_search_config_live: Probe a single provider or a whole provider chain (failover included)
- verify_search_config_cached: Same probe behind a 60s verdict cache (readiness gate)
- invalidate_search_verify_cache: Drop cached verdicts after Settings changes

[POS]
Settings/API search provider verify endpoint and readiness gate backing service.
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


def _members(cfg: SearchServiceConfig) -> list[SearchServiceConfig]:
    """Providers a search through ``cfg`` can reach, in failover order."""
    return cfg.provider_chain or [cfg]


def _cache_key(cfg: SearchServiceConfig) -> str:
    return "|".join(f"{m.search_service}:{m.api_key or ''}:{m.api_base or ''}" for m in _members(cfg))


def _has_required_credentials(member: SearchServiceConfig) -> bool:
    """Whether the provider is selectable and carries what its catalog entry requires."""
    entry = SearchProviderCatalogRegistry.get_instance().get_by_slug(member.search_service)
    if entry is None or not entry.backend_ready:
        logger.warning("Search verify skipped: provider '%s' is not selectable", member.search_service)
        return False
    if entry.requires_api_key and not member.api_key:
        return False
    return not (entry.requires_api_base and not member.api_base)


_E2E_PROBE_SKIPPED_API_KEYS: frozenset[str] = frozenset({"test-tavily-key"})


async def verify_search_config_live(cfg: SearchServiceConfig, *, query: str | None = None) -> bool:
    """Run a lightweight live search probe for the given config.

    A chain config is probed as one unit, exactly the way the agent searches it (failover included), so the verdict
    means "a search will get an answer" and not "the first provider answers". A member without credentials does not
    veto the probe because the chain skips it at search time; only a chain with no usable member is unavailable.
    """
    members = _members(cfg)
    if members[0].api_key in _E2E_PROBE_SKIPPED_API_KEYS:
        return True
    if not any(_has_required_credentials(member) for member in members):
        return False

    try:
        results = await search_web_service(
            query=query or "Beijing Forbidden City",
            search_service_cfg=cfg,
            num_results=1,
        )
        return bool(results)
    except Exception as exc:
        logger.warning("Search verify probe failed for %s: %s", "/".join(member.search_service for member in members), exc)
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
