"""Database Subagent Catalog Implementation.

Resolves subagent configurations from YAML presets or database.
When loading custom agents from DB as subagents:
  - Injects CustomAgentFactory to build a full SkillAgent (with skills, memory, MCP)
  - Enforces LEAF control scope (no recursive delegation)
  - Enforces READ_ONLY_GLOBAL memory isolation (prevent concurrent state pollution)

For YAML presets, injects a ModelResolver so config.model can be resolved
to an actual LLM instance instead of silently falling back to parent LLM.
"""

import logging
from dataclasses import replace

from myrm_agent_harness.agent.sub_agents.registry import auto_register_subagent_configs
from myrm_agent_harness.agent.sub_agents.types import (
    ControlScope,
    MemoryIsolationPolicy,
    SubagentConfig,
    WorkspacePolicy,
)

from app.platform_utils import get_session_factory
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)

_WP_MAP: dict[str, WorkspacePolicy] = {
    "ISOLATED_COPY": WorkspacePolicy.ISOLATED_COPY,
    "READ_ONLY_SANDBOX": WorkspacePolicy.READ_ONLY_SANDBOX,
}


class _LLMModelResolver:
    """ModelResolver implementation using the business layer's model resolver.

    Resolves model_name (LiteLLM format like "openai/gpt-4o-mini") to a
    BaseChatModel by looking up the user's provider config for API keys.
    """

    def __init__(self) -> None:
        pass

    async def resolve(self, model_name: str) -> object:
        from myrm_agent_harness.toolkits.llms import llm_manager

        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.model_resolver import resolve_model_config

        configs = await load_user_configs()
        providers_dict = configs.providers_dict if configs else None
        model_cfg = resolve_model_config(providers_dict, model_override=model_name)
        return await llm_manager.get_llm_from_config(model_cfg, api_keys=getattr(model_cfg, "api_keys", None))


class DatabaseSubagentCatalog:
    """Subagent catalog: YAML presets + database custom agents.

    For YAML presets, injects model_resolver so config.model can be resolved.
    For DB custom agents, injects CustomAgentFactory so that build_child_agent()
    creates a SkillAgent with full capabilities instead of a bare BaseAgent.

    Scope restriction: When bound_agent_ids is provided, only those IDs
    (plus YAML presets) are available. This prevents arbitrary cross-calling.
    """

    def __init__(
        self,
        bound_agent_ids: list[str] | None = None,
        jit_configs: dict[str, SubagentConfig] | None = None,
    ):
        self._bound_agent_ids = set(bound_agent_ids) if bound_agent_ids is not None else None
        self._jit_configs = jit_configs or {}
        self._model_resolver = _LLMModelResolver()

        from pathlib import Path

        config_dir = Path(__file__).parent.parent / "config" / "subagents"
        try:
            self._yaml_configs = auto_register_subagent_configs(base_path=str(config_dir))
        except Exception as e:
            logger.warning("Failed to load YAML subagent configs: %s", e)
            self._yaml_configs = {}

    async def resolve(self, type_id: str) -> SubagentConfig | None:
        """Resolve a subagent configuration by type_id or agent_id."""
        if type_id in self._jit_configs:
            cfg = self._jit_configs[type_id]
            if cfg.model and cfg.model_resolver is None:
                return replace(cfg, model_resolver=self._model_resolver)
            return cfg

        if type_id in self._yaml_configs:
            cfg = self._yaml_configs[type_id]
            if cfg.model and cfg.model_resolver is None:
                return replace(cfg, model_resolver=self._model_resolver)
            return cfg

        if self._bound_agent_ids is not None and type_id not in self._bound_agent_ids:
            logger.warning("Agent '%s' not in bound_agent_ids, rejecting", type_id)
            return None

        try:
            session_factory = get_session_factory()
            async with session_factory() as _db:
                agent_profile = await AgentService.get_agent_by_id(type_id)
                if not agent_profile:
                    return None

                from app.ai_agents.custom_agent_factory import CustomAgentFactory

                factory = CustomAgentFactory(
                    agent_id=type_id,
                    agent_profile=agent_profile,
                )

                max_turns = agent_profile.max_iterations or 25
                raw_workspace_policy = (agent_profile.metadata or {}).get("workspace_policy")
                workspace_policy = _WP_MAP.get(str(raw_workspace_policy), WorkspacePolicy.INHERIT) if raw_workspace_policy else WorkspacePolicy.INHERIT

                return SubagentConfig(
                    system_prompt=agent_profile.system_prompt or "",
                    description=agent_profile.description or "",
                    display_name=agent_profile.display_name or "",
                    model=agent_profile.model,
                    max_turns=max_turns,
                    control_scope=ControlScope.LEAF,
                    memory_isolation=MemoryIsolationPolicy.READ_ONLY_GLOBAL,
                    max_spawn_depth=0,
                    workspace_policy=workspace_policy,
                    agent_factory=factory,
                )
        except Exception as e:
            logger.error("Failed to resolve subagent from database for type_id=%s: %s", type_id, e)
            return None

    async def list_available(self) -> list[str]:
        """List available subagent type IDs (JIT + YAML + bound DB agents)."""
        available = list(self._jit_configs.keys()) + list(self._yaml_configs.keys())

        if self._bound_agent_ids is not None:
            available.extend(sorted(self._bound_agent_ids))
        else:
            try:
                session_factory = get_session_factory()
                async with session_factory() as _db:
                    profiles, _ = await AgentService.get_agent_list(page=1, page_size=1000)
                    available.extend([p.id for p in profiles])
            except Exception as e:
                logger.error("Failed to list available subagents from database: %s", e)

        return available
