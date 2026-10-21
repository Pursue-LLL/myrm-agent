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

import asyncio
import logging
import time

from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig

from app.core.integrations.search_catalog.registry import SearchProviderCatalogRegistry
from app.services.agent.search import search_web_service

logger = logging.getLogger(__name__)

_VERIFY_TTL_SECONDS = 60.0
_PROBE_WALL_CLOCK_SECONDS = 25.0
_verify_cache: dict[str, tuple[float, bool]] = {}


def _members(cfg: SearchServiceConfig) -> list[SearchServiceConfig]:
    """Providers a search through ``cfg`` can reach, in failover order."""
    return cfg.provider_chain or [cfg]


def _member_identity(member: SearchServiceConfig) -> str:
    """Everything about one chain member that decides which answer a search comes back with.

    The gateway endpoint and token belong here alongside the provider key: two agents routed through different
    gateway tokens have different quota and can be answered differently, so one verdict must not serve both.
    """
    gateway = member.gateway_config
    gateway_scope = f"{gateway.gateway_url or ''}:{gateway.auth_token or ''}" if gateway and gateway.use_gateway else ""
    return f"{member.search_service}:{member.api_key or ''}:{member.api_base or ''}:{gateway_scope}"


def _cache_key(cfg: SearchServiceConfig) -> str:
    return "|".join(_member_identity(member) for member in _members(cfg))


def _has_required_credentials(member: SearchServiceConfig) -> bool:
    """Whether the provider is selectable and carries what its catalog entry requires."""
    entry = SearchProviderCatalogRegistry.get_instance().get_by_slug(member.search_service)
    if entry is None or not entry.backend_ready:
        logger.warning("Search verify skipped: provider '%s' is not selectable", member.search_service)
        return False
    if entry.requires_api_key and not member.api_key:
        return False
    return not (entry.requires_api_base and not member.api_base)


async def verify_search_config_live(cfg: SearchServiceConfig, *, query: str | None = None) -> bool:
    """Run a lightweight live search probe for the given config.

    A chain config is probed as one unit, exactly the way the agent searches it (failover included), so the verdict
    means "a search will get an answer" and not "the first provider answers". A member without credentials does not
    veto the probe because the chain skips it at search time; only a chain with no usable member is unavailable.

    Every configured credential is probed for real: no value may excuse a hop from the probe, because a verdict of
    "available" that no request produced would let a dead credential through the readiness gate.

    The probe gives up on its own wall clock: a provider that accepts the connection but never answers would
    otherwise hold the caller for its full retry budget (seconds to about a minute) on every cache window.
    """
    members = _members(cfg)
    if not any(_has_required_credentials(member) for member in members):
        return False

    chain_slugs = "/".join(member.search_service for member in members)
    try:
        async with asyncio.timeout(_PROBE_WALL_CLOCK_SECONDS):
            results = await search_web_service(
                query=query or "Beijing Forbidden City",
                search_service_cfg=cfg,
                num_results=1,
            )
        return bool(results)
    except TimeoutError:
        logger.warning("Search verify probe exceeded %.0fs for %s", _PROBE_WALL_CLOCK_SECONDS, chain_slugs)
        return False
    except Exception as exc:
        logger.warning("Search verify probe failed for %s: %s", chain_slugs, exc)
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
