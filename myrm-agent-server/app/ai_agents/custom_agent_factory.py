"""CustomAgentFactory — builds SkillAgent instances for custom subagents.

[INPUT]
- myrm_agent_harness.agent.sub_agents.types::SubagentConfig (POS: subagent runtime contract)
- app.core.memory.adapters.setup::create_memory_manager (POS: Server memory manager adapter factory)
- app.core.skills.loader::create_skill_backend (POS: the profile's skill backend, gated for one credential track)
- app.ai_agents.subagent_assembly (POS: tool boundary, security inheritance, memory rebind and write backend shared with EphemeralAgentFactory)

[OUTPUT]
- CustomAgentFactory: DB-backed custom subagent factory

[POS]
Custom subagent assembly layer. Builds isolated SkillAgent instances and rebinds the inherited memory_search_tool to the
subagent's own memory only, so a delegated subagent never inherits the parent's wiki or past-conversation corpora.

When a custom agent (configured by the user in the frontend) is delegated
as a subagent via delegate_task, the framework's build_child_agent() calls
this factory to construct a fully-featured SkillAgent instead of a bare
BaseAgent.

This enables custom subagents to retain their full capabilities: skills,
memory, and MCP integrations.

Resources (skill_backend, MCP configs) are initialized
once on first build() and cached for reuse within the same session.

The delegated agent runs inside the delegating turn, so it is handed that turn's credentials: its skill backend is
gated for the same credential track, and a skill that needs a credential the track cannot obtain is not offered.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

from myrm_agent_harness.agent.security import CredentialTrack
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
    from myrm_agent_harness.backends.skills.protocols import SkillBackend
    from myrm_agent_harness.toolkits.mcp.config import MCPConfig
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

    from app.core.types import MCPServerConfig

logger = logging.getLogger(__name__)
_EPHEMERAL_MEMORY_ISOLATION = "ephemeral_session"


def _coerce_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
    return out


def _coerce_str_frozenset(value: object) -> frozenset[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str))


class CustomAgentFactory:
    """AgentFactory implementation that creates SkillAgent from DB profile.

    Loads the full agent configuration (skills, model, MCP)
    from the database and constructs a SkillAgent via create_skill_agent().

    Resources are lazily initialized on first build() and cached for reuse
    when the same custom agent is delegated multiple times in a session.
    """

    __slots__ = (
        "_agent_id",
        "_agent_profile",
        "_credential_track",
        "_init_lock",
        "_cached_skill_backend",
        "_cached_mcp_configs",
        "_initialized",
    )

    def __init__(
        self,
        agent_id: str,
        agent_profile: object,
        *,
        credential_track: CredentialTrack = CredentialTrack.PERSONAL,
    ) -> None:
        self._agent_id = agent_id
        self._agent_profile = agent_profile
        self._credential_track = credential_track
        self._init_lock = asyncio.Lock()
        self._cached_skill_backend: SkillBackend | None = None
        self._cached_mcp_configs: list[MCPServerConfig] = []
        self._initialized = False

    @staticmethod
    async def _resolve_embedding_config() -> EmbeddingConfig | None:
        """Resolve embedding config from WebUI retrieval settings."""
        from app.services.agent.platform_config import load_platform_retrieval_configs

        embedding_cfg, _ = await load_platform_retrieval_configs()
        return embedding_cfg

    async def _ensure_initialized(self) -> None:
        """Initialize cached resources (skill backend, KB tools, MCP configs).

        Thread-safe via asyncio.Lock. Idempotent — skips if already done.
        """
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            profile = self._agent_profile
            metadata: dict[str, object] = getattr(profile, "metadata", None) or {}

            from app.core.skills.effective_skill_ids import resolve_runtime_skill_ids
            from app.core.skills.loader import create_skill_backend
            from app.core.skills.store.user_config import UserSkillConfigManager
            from app.platform_utils import get_storage_provider

            storage_backend = get_storage_provider()
            skill_ids = await resolve_runtime_skill_ids(getattr(profile, "skills", None) or [])
            # Keep custom subagents in the same prebuilt-visibility contract as GeneralAgent:
            # only user-enabled prebuilt skills are loaded into runtime action space.
            user_skill_cfg = await UserSkillConfigManager(storage_backend).get_config()
            allowed_prebuilt = _coerce_str_frozenset(getattr(user_skill_cfg, "enabled_prebuilt_ids", []))

            self._cached_skill_backend = await create_skill_backend(
                storage=storage_backend,
                skill_ids=skill_ids or None,
                user_id="default",
                allowed_prebuilt_ids=allowed_prebuilt,
                credential_track=self._credential_track,
            )

            mcp_ids = _coerce_str_list(metadata.get("mcp_ids", []))
            if mcp_ids:
                try:
                    from app.core.channel_bridge.config_loader import load_user_configs
                    from app.core.channel_bridge.config_parsers import (
                        extract_mcp_configs,
                        merge_org_mcp_configs,
                    )
                    from app.services.agent.params.mcp_selection import (
                        apply_agent_mcp_selection,
                        coerce_tool_selections,
                    )

                    configs = await load_user_configs()
                    if configs:
                        all_mcp = merge_org_mcp_configs(
                            extract_mcp_configs(configs.mcp_dict),
                            configs.org_mcp_dict,
                        )
                        tool_selections = coerce_tool_selections(metadata.get("mcp_tool_selections"))
                        self._cached_mcp_configs = apply_agent_mcp_selection(
                            all_mcp,
                            mcp_ids=tuple(mcp_ids),
                            mcp_tool_selections=tool_selections,
                        )
                except Exception as e:
                    logger.warning("[CustomAgentFactory] MCP config resolution failed: %s", e)

            self._initialized = True

    async def build(
        self,
        config: SubagentConfig,
        tools: list[object],
        task_description: str,
        parent_agent: object,
        current_depth: int,
        complexity_tier: str | None = None,
    ) -> BaseAgent:
        """Build a SkillAgent with full custom agent capabilities."""
        from myrm_agent_harness.api import create_skill_agent
        from myrm_agent_harness.toolkits.llms import llm_manager

        from app.ai_agents.general_agent.tools import ensure_tool_layer_bootstrap
        from app.platform_utils import get_storage_provider
        from app.services.agent.tool_mount import resolve_child_meta_mount

        # A subagent can be the first agent built in this process, and tool layers are registered on
        # first use rather than at HTTP import time, so await the same idempotent bootstrap here.
        await asyncio.to_thread(ensure_tool_layer_bootstrap)

        await self._ensure_initialized()
        profile = self._agent_profile

        # 10/10 Scheme: If context is forked, we MUST drop the system_prompt entirely.
        # Otherwise, LangGraph prepends a new SystemMessage, shifting the array and breaking Prefix Cache!
        if getattr(config, "context_mode", "isolated") == "fork":
            system_prompt = ""
        else:
            system_prompt = config.system_prompt or ""

        # NOT appending task_description to system_prompt to preserve prefix cache (cache_control).

        # --- 1. Resolve LLM ---
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
                    "[CustomAgentFactory] Failed to resolve model '%s', falling back to parent LLM: %s",
                    config.model,
                    e,
                )
        if llm is None:
            llm = cast("BaseAgent", parent_agent).llm

        # --- 2. Memory Manager (respects memory_isolation policy) ---
        memory_manager = None
        if str(getattr(config, "memory_isolation", _EPHEMERAL_MEMORY_ISOLATION)) != _EPHEMERAL_MEMORY_ISOLATION:
            try:
                from app.core.memory.adapters.setup import (
                    create_memory_manager,
                    resolve_context_binding,
                )
                from app.services.memory.extract_retry.resolve_chat_extraction_llm import (
                    get_platform_dedup_llm,
                )

                # embedding_cfg is None on a default install: the manager then runs in keyword mode.
                embedding_cfg = await self._resolve_embedding_config()
                dedup_llm = await get_platform_dedup_llm() or llm
                memory_manager = await create_memory_manager(
                    resolve_context_binding(
                        namespaces=None,
                        agent_id=self._agent_id,
                        channel_id=None,
                        conversation_id=None,
                        task_id=None,
                        project_id=getattr(config, "project_id", None) or getattr(self, "_project_id", None),
                        memory_policy=getattr(profile, "memory_policy", None),
                    ),
                    embedding_config=embedding_cfg,
                    dedup_llm=dedup_llm,
                )
            except Exception as e:
                logger.warning(
                    "[CustomAgentFactory] Memory manager creation failed (degraded to no-memory): %s",
                    e,
                )

        # --- 3. Max iterations ---
        max_iterations = getattr(profile, "max_iterations", None) or 100

        # --- 4. Build AgentRuntimeSpec & create SkillAgent ---
        from app.core.skills.effective_skill_ids import resolve_runtime_skill_ids

        skill_ids = await resolve_runtime_skill_ids(getattr(profile, "skills", None) or [])

        profile_metadata: dict[str, object] = getattr(profile, "metadata", None) or {}
        raw_engine_params = profile_metadata.get("engine_params")
        engine_params: dict[str, object] | None = dict(raw_engine_params) if isinstance(raw_engine_params, dict) else None
        raw_openapi = profile_metadata.get("openapi_services")
        openapi_services: list[dict[str, object]] = (
            [item for item in raw_openapi if isinstance(item, dict)] if isinstance(raw_openapi, list) else []
        )
        from app.services.agent.mcp_surface_mode import (
            normalize_mcp_surface_engine_params,
        )

        mcp_surface_mode, engine_params = normalize_mcp_surface_engine_params(engine_params)

        from app.services.agent.params.response_locale_suffix import (
            apply_response_locale_suffix,
        )

        system_prompt = apply_response_locale_suffix(system_prompt, engine_params=engine_params) or system_prompt

        mcp_servers = list(self._cached_mcp_configs)
        if mcp_servers:
            from app.services.agent.mcp_runtime_prepare import (
                prepare_mcp_configs_for_runtime,
            )

            mcp_servers = await prepare_mcp_configs_for_runtime(
                self._agent_id,
                mcp_servers,
            )

        spec = AgentRuntimeSpec(
            agent_id=self._agent_id,
            name=getattr(profile, "display_name", None) or self._agent_id,
            system_prompt=system_prompt,
            skill_ids=skill_ids,
            mcp_servers=cast("list[MCPConfig]", mcp_servers),
            openapi_services=openapi_services,
            engine_params=engine_params,
            mcp_surface_mode=mcp_surface_mode,
            max_iterations=max_iterations,
            security_config=inherit_parent_security_config(parent_agent),
        )

        enabled_builtin = getattr(profile, "enabled_builtin_tools", ())
        all_tools = filter_tools_by_profile(list(cast("list[BaseTool]", tools)), enabled_builtin)
        apply_subagent_memory_search_rebind(
            all_tools,
            parent_agent=parent_agent,
            memory_manager=memory_manager,
            enabled_builtin=tuple(enabled_builtin),
        )

        storage_backend = get_storage_provider()
        agent = await create_skill_agent(
            spec=spec,
            llm=llm,
            executor=cast("BaseAgent", parent_agent).executor,
            storage_backend=storage_backend,
            skill_backend=self._cached_skill_backend,
            write_backend=subagent_write_backend(config),
            memory_manager=memory_manager,
            tools=all_tools,
            collect_artifacts=False,
            checkpointer=get_subagent_checkpointer(),
            **resolve_child_meta_mount(),
        )

        logger.info(
            "[CustomAgentFactory] Built SkillAgent for '%s': skills=%d, tools=%d, memory=%s, mcp=%d",
            self._agent_id,
            len(skill_ids),
            len(all_tools),
            config.memory_isolation.value,
            len(mcp_servers),
            extra={"complexity_tier": complexity_tier, "current_depth": current_depth},
        )
        return agent
