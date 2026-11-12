"""[INPUT]
- myrm_agent_harness.toolkits.web_search::SearchServiceConfig / SearchServiceConfig / SearchServiceConfig (POS: Web search toolkit entry point. Aggregates and re-exports search tools, result types, and error hierarchy for unified import.)
- app.services.integrations.search_verify::verify_search_config_cached (POS: Settings/API search provider verify endpoint and readiness gate backing service.)
- app.core.integrations.search_catalog.migration::migrate_search_service_configs (POS: One-time search catalog config migration for Omni searchServices schema.)
- app.core.integrations.search_catalog.registry::SearchProviderCatalogRegistry (POS: Server-side search provider catalog SSOT for Settings UI and verify probes.)

[OUTPUT]
- is_search_user_configured: Check whether the user has explicitly configured and enabled a search service.
- verify_search_service_available: Live probe of the configured search providers behind a short verdict cache.
- extract_search_provider_chain: Extract enabled search configs sorted by priority (1 = highest).
- extract_active_search_config: Extract active search config with priority provider chain attached.

[POS]
channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig


logger = logging.getLogger(__name__)


def is_search_user_configured(search_services_dict: dict[str, object] | None) -> bool:
    """Check whether the user has explicitly configured and enabled a search service."""
    if not search_services_dict:
        return False
    configs = search_services_dict.get("searchServiceConfigs")
    if not isinstance(configs, list) or not configs:
        return False
    return any(isinstance(c, dict) and c.get("enabled") for c in configs)


async def verify_search_service_available(cfg: "SearchServiceConfig | None") -> bool:
    """Live probe of the configured search providers behind a short verdict cache.

    A provider chain is probed the way the agent searches it, so one dead provider does not make search unavailable
    while another one in the chain still answers.
    """
    if cfg is None:
        return False

    from app.services.integrations.search_verify import verify_search_config_cached

    return await verify_search_config_cached(cfg)


def extract_search_provider_chain(
    search_services_dict: dict[str, object] | None,
) -> list["SearchServiceConfig"]:
    """Extract enabled search configs sorted by priority (1 = highest)."""
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    from app.core.integrations.search_catalog.migration import (
        migrate_search_service_configs,
    )
    from app.core.integrations.search_catalog.registry import (
        SearchProviderCatalogRegistry,
    )

    if not search_services_dict:
        return []

    if isinstance(search_services_dict, str):
        import json

        try:
            search_services_dict = json.loads(search_services_dict)
        except Exception:
            return []
    if not isinstance(search_services_dict, dict):
        return []

    configs = search_services_dict.get("searchServiceConfigs")
    if not isinstance(configs, list) or not configs:
        return []

    dict_configs = [c for c in configs if isinstance(c, dict)]
    migrated = migrate_search_service_configs(dict_configs)
    enabled = [c for c in migrated if c.get("enabled")]
    if not enabled:
        return []

    registry = SearchProviderCatalogRegistry.get_instance()
    max_chain = registry.max_chain_size()

    def _priority(row: dict[str, object]) -> int:
        raw = row.get("priority", 999)
        return int(raw) if isinstance(raw, int) else 999

    enabled.sort(key=_priority)
    chain: list[SearchServiceConfig] = []
    for row in enabled[:max_chain]:
        slug = str(row.get("search_service", ""))
        if not registry.is_selectable_slug(slug):
            continue
        extra_params = row.get("extra_params")
        chain.append(
            SearchServiceConfig(
                search_service=slug,
                api_key=str(row["api_key"]) if row.get("api_key") else None,
                api_base=str(row["api_base"]) if row.get("api_base") else None,
                extra_params=extra_params if isinstance(extra_params, dict) else None,
            )
        )
    return chain


def extract_active_search_config(
    search_services_dict: dict[str, object] | None,
) -> "SearchServiceConfig | None":
    """Extract active search config with priority provider chain attached."""
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    chain = extract_search_provider_chain(search_services_dict)
    if not chain:
        logger.warning("config_parsers: no enabled search provider chain in WebUI Settings")
        return None

    head = chain[0]
    return SearchServiceConfig(
        search_service=head.search_service,
        api_key=head.api_key,
        api_base=head.api_base,
        extra_params=head.extra_params,
        provider_chain=chain,
    )
