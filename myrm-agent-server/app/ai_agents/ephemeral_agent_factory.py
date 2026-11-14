"""EphemeralAgentFactory — builds SkillAgent instances for in-memory (blueprint) subagents.

[INPUT]
- myrm_agent_harness.agent.sub_agents.types::SubagentConfig (POS: subagent runtime contract)
- app.ai_agents.subagent_assembly (POS: tool boundary, security inheritance, memory rebind and write backend shared with CustomAgentFactory)

[OUTPUT]
- EphemeralAgentFactory: in-memory JIT subagent factory

[POS]
Subagent assembly for 'Scenario Blueprint' ephemeral teams. Constructs a SkillAgent purely from the blueprint's
in-memory configuration without touching the database: no skills, no MCP servers, no memory manager of its own. The
inherited memory_search_tool is rebound like CustomAgentFactory does, so a delegated subagent never inherits the
parent's wiki or past-conversation corpora.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from myrm_agent_harness.api import AgentRuntimeSpec, get_subagent_checkpointer

from app.ai_agents.subagent_assembly import (
    apply_subagent_memory_search_rebind,
    filter_tools_by_profile,
    inherit_parent_security_config,
    subagent_write_backend,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.base_agent import BaseAgent
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

logger = logging.getLogger(__name__)


class EphemeralAgentFactory:
    """AgentFactory implementation for in-memory JIT subagents.

    Constructs a SkillAgent purely from memory configurations without hitting
    the database. Used for 'Scenario Blueprint' ephemeral teams.
    """

    __slots__ = ("_agent_id", "_metadata")

    def __init__(self, agent_id: str, metadata: dict[str, object] | None = None) -> None:
        self._agent_id = agent_id
        self._metadata = metadata or {}

    async def build(
        self,
        config: SubagentConfig,
        tools: list[object],
        task_description: str,
        parent_agent: object,
        current_depth: int,
        complexity_tier: str | None = None,
    ) -> BaseAgent:

        from myrm_agent_harness.api import create_skill_agent
        from myrm_agent_harness.toolkits.llms import llm_manager

        from app.platform_utils import get_storage_provider
        from app.services.agent.tool_mount import resolve_child_meta_mount

        # 10/10 Scheme: If context is forked, we MUST drop the system_prompt entirely.
        # Otherwise, LangGraph prepends a new SystemMessage, shifting the array and breaking Prefix Cache!
        if getattr(config, "context_mode", "isolated") == "fork":
            system_prompt = ""
        else:
            system_prompt = config.system_prompt or ""

        # NOT appending task_description to system_prompt to preserve prefix cache (cache_control).

        llm: BaseChatModel | None = None
        if config.llm is not None:
            llm = cast("BaseChatModel", config.llm)
        elif config.model:
            try:
                from app.core.channel_bridge.config_loader import load_user_configs
                from app.core.channel_bridge.model_resolver import resolve_model_config

                configs = await load_user_configs()
                providers_dict = configs.providers_dict if configs else None
                model_cfg = resolve_model_config(
                    providers_dict,
                    model_override=config.model,
                )
                llm = await llm_manager.get_llm_from_config(model_cfg, api_keys=getattr(model_cfg, "api_keys", None))
            except Exception as e:
                logger.warning(
                    "[EphemeralAgentFactory] Failed to resolve model '%s': %s",
                    config.model,
                    e,
                )

        if llm is None:
            llm = getattr(parent_agent, "llm", None)

        spec = AgentRuntimeSpec(
            agent_id=self._agent_id,
            name=config.display_name or self._agent_id,
            system_prompt=system_prompt,
            skill_ids=[],
            mcp_servers=[],
            max_iterations=config.max_turns,
            security_config=inherit_parent_security_config(parent_agent),
        )

        raw_builtin = self._metadata.get("enabled_builtin_tools")
        if not isinstance(raw_builtin, (list, tuple)):
            from app.services.agent.profile.profile_resolver import (
                DEFAULT_ENABLED_BUILTIN_TOOLS,
            )

            raw_builtin = DEFAULT_ENABLED_BUILTIN_TOOLS
        enabled_builtin = tuple(str(x) for x in raw_builtin)
        all_tools = filter_tools_by_profile(list(cast("list[BaseTool]", tools)), enabled_builtin)
        apply_subagent_memory_search_rebind(
            all_tools,
            parent_agent=parent_agent,
            memory_manager=getattr(parent_agent, "memory_manager", None),
            enabled_builtin=enabled_builtin,
        )

        agent = await create_skill_agent(
            spec=spec,
            llm=llm,
            executor=getattr(parent_agent, "executor", None),
            storage_backend=get_storage_provider(),
            skill_backend=None,
            write_backend=subagent_write_backend(config),
            memory_manager=None,
            tools=all_tools,
            collect_artifacts=False,
            checkpointer=get_subagent_checkpointer(),
            **resolve_child_meta_mount(),
        )

        logger.info(
            "[EphemeralAgentFactory] Built in-memory SkillAgent for '%s'",
            self._agent_id,
            extra={"complexity_tier": complexity_tier, "current_depth": current_depth},
        )
        return agent
