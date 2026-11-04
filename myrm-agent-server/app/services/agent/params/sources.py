"""[INPUT]
- app.services.agent.params.models::AgentRequest (POS: Agent API request DTO)
- app.core.channel_bridge.config_loader::UserConfigs (POS: decrypted user config bundle)
- app.core.channel_bridge.config_parsers (POS: search / retrieval / MCP config extractors)

[OUTPUT]
- ConfigSources: search service, retrieval models and MCP servers for one agent turn
- resolve_config_sources(): request override first, then the saved user configuration

[POS]
External data-source resolution stage of Agent request conversion. Everything the agent reads
from the outside world (web search, embeddings/reranker, MCP servers) is assembled here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.types import MCPServerConfig

from .models import AgentRequest

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    from app.core.channel_bridge.config_loader import UserConfigs

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ConfigSources:
    """Resolved external data sources for one agent turn."""

    search_cfg: SearchServiceConfig | None
    search_available: bool
    search_is_user_configured: bool
    embedding_cfg: EmbeddingConfig | None
    reranker_cfg: RerankerConfig | None
    mcp_configs: list[MCPServerConfig] | None


async def resolve_config_sources(request: AgentRequest, configs: UserConfigs | None) -> ConfigSources:
    """Resolve search availability, retrieval models and MCP servers."""

    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.core.channel_bridge.config_loader import load_user_configs as reload_user_configs
    from app.core.channel_bridge.config_parsers import (
        extract_mcp_configs,
        extract_retrieval_models,
        merge_org_mcp_configs,
        verify_search_service_available,
    )

    search_cfg = configs.search_cfg if configs else None
    search_available = False
    if search_cfg is None and configs is not None:
        # SHPOIB E2E seeds searchServices on the private API immediately before kickoff;
        # bypass stale config-cache reads so web_search_tool mounts on the same agent turn.
        invalidate_user_configs_cache()
        refreshed_configs = await reload_user_configs()
        if refreshed_configs is not None and refreshed_configs.search_cfg is not None:
            configs = refreshed_configs
            search_cfg = refreshed_configs.search_cfg
    if configs and configs.search_is_user_configured and search_cfg is not None:
        search_available = await verify_search_service_available(search_cfg)

    if request.retrieval_dict:
        embedding_cfg, reranker_cfg = extract_retrieval_models(request.retrieval_dict)
    else:
        embedding_cfg, reranker_cfg = extract_retrieval_models(configs.retrieval_dict) if configs else (None, None)

    if embedding_cfg is None and reranker_cfg is None:
        logger.debug("No embedding/reranker config in request or user retrieval settings")

    mcp_configs: list[MCPServerConfig] | None = None
    if request.mcp_cfg:
        mcp_configs = [MCPServerConfig.model_validate(d) for d in request.mcp_cfg]
    elif configs and configs.mcp_dict:
        mcp_configs = extract_mcp_configs(configs.mcp_dict) or None

    # Append org-level MCP servers (read-only, pushed by Control Plane)
    if configs:
        mcp_configs = merge_org_mcp_configs(mcp_configs, configs.org_mcp_dict) or None

    return ConfigSources(
        search_cfg=search_cfg,
        search_available=search_available,
        search_is_user_configured=bool(configs and configs.search_is_user_configured),
        embedding_cfg=embedding_cfg,
        reranker_cfg=reranker_cfg,
        mcp_configs=mcp_configs,
    )
