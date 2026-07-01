"""CustomAgentFactory — builds SkillAgent instances for custom subagents.

[INPUT]
myrm_agent_harness.agent.sub_agents.types::SubagentConfig (POS: subagent runtime contract)
app.core.memory.adapters.setup::create_memory_manager (POS: Server memory manager adapter factory)
app.services.chat.conversation_search_service::ConversationHistorySearchProvider (POS: 会话历史召回服务。将 Server 的 Chat DB、FTS5、预计算摘要与 Harness MemoryManager 语义召回组合为 agent 可用的只读工具能力)
myrm_agent_harness.toolkits.memory.conversation_search::create_conversation_search_tool (POS: framework-level conversation recall tool factory)

[OUTPUT]
CustomAgentFactory: DB-backed custom subagent factory.
EphemeralAgentFactory: in-memory JIT subagent factory.

[POS]
Custom subagent assembly layer. Builds isolated SkillAgent instances and prevents delegated agents from inheriting
the parent agent's global conversation history search surface.

When a custom agent (configured by the user in the frontend) is delegated
as a subagent via delegate_task, the framework's build_child_agent() calls
this factory to construct a fully-featured SkillAgent instead of a bare
BaseAgent.

This enables custom subagents to retain their full capabilities: skills,
memory, MCP integrations, and personality style.

Resources (skill_backend, MCP configs) are initialized
once on first build() and cached for reuse within the same session.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig
from myrm_agent_harness.api import AgentRuntimeSpec

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.base_agent import BaseAgent

logger = logging.getLogger(__name__)


def _coerce_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
    return out


def _filter_tools_by_profile(tools: list[object], enabled_builtin_tools: tuple[str, ...]) -> list[object]:
    """Filter inherited tools based on the active agent's tool boundaries."""
    from myrm_agent_harness.core.security.tool_registry import TOOL_TO_GROUP

    active_groups = set()
    if "web_search" in enabled_builtin_tools:
        active_groups.add("web")
    if "browser" in enabled_builtin_tools:
        active_groups.add("browser")
    if "file_ops" in enabled_builtin_tools:
        active_groups.add("file_ops")
    if "code_execute" in enabled_builtin_tools:
        active_groups.add("shell")
    if "computer_use" in enabled_builtin_tools:
        active_groups.add("computer_use")
    if "memory" in enabled_builtin_tools:
        active_groups.add("memory")
    if "kanban" in enabled_builtin_tools:
        active_groups.add("kanban")
    if "wiki" in enabled_builtin_tools:
        active_groups.add("wiki")

    filtered = []
    for t in tools:
        t_name = getattr(t, "name", "")
        t_group = TOOL_TO_GROUP.get(t_name)
        # If the tool is part of a canonical group but the group is not enabled, filter it out
        if t_group is not None and t_group not in active_groups:
            continue
        filtered.append(t)
    return filtered


def _without_inherited_conversation_search(tools: list[object]) -> list[object]:
    """Prevent delegated agents from inheriting the parent's global chat-history tool."""

    return [tool for tool in tools if getattr(tool, "name", "") != "conversation_search_tool"]


def _parent_chat_id(parent_agent: object) -> str | None:
    last_context = getattr(parent_agent, "_last_context", None)
    if not isinstance(last_context, dict):
        return None
    chat_id = last_context.get("chat_id") or last_context.get("session_id")
    return chat_id if isinstance(chat_id, str) and chat_id else None


def _append_scoped_conversation_search(
    tools: list[object],
    *,
    current_chat_id: str | None,
    agent_id: str,
    memory_manager: object | None,
) -> None:
    """Attach Server-governed conversation search for a custom subagent."""

    if memory_manager is None:
        return
    from myrm_agent_harness.toolkits.memory.conversation_search import (
        create_conversation_search_tool,
    )
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

    from app.services.chat.conversation_search_service import ConversationHistorySearchProvider

    if not isinstance(memory_manager, MemoryManager):
        return
    provider = ConversationHistorySearchProvider(
        current_chat_id=current_chat_id,
        agent_id=agent_id,
        memory_manager=memory_manager,
    )
    tools.append(create_conversation_search_tool(provider))


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
        "_init_lock",
        "_cached_skill_backend",
        "_cached_mcp_configs",
        "_initialized",
    )

    def __init__(
        self,
        agent_id: str,
        agent_profile: object,
    ) -> None:
        self._agent_id = agent_id
        self._agent_profile = agent_profile
        self._init_lock = asyncio.Lock()
        self._cached_skill_backend: object | None = None
        self._cached_mcp_configs: list[object] = []
        self._initialized = False

    @staticmethod
    async def _resolve_embedding_config() -> object | None:
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

            from app.core.skills.loader import create_skill_backend
            from app.platform_utils import get_storage_provider

            storage_backend = get_storage_provider()
            skill_ids: list[str] = getattr(profile, "skills", None) or []

            self._cached_skill_backend = await create_skill_backend(
                storage=storage_backend,
                skill_ids=skill_ids or None,
            )

            mcp_ids = _coerce_str_list(metadata.get("mcp_ids", []))
            if mcp_ids:
                try:
                    from app.core.channel_bridge.config_loader import load_user_configs
                    from app.core.channel_bridge.config_parsers import extract_mcp_configs
                    from app.services.agent.params.mcp_selection import (
                        apply_agent_mcp_selection,
                        coerce_tool_selections,
                    )

                    configs = await load_user_configs()
                    if configs and configs.mcp_dict:
                        all_mcp = extract_mcp_configs(configs.mcp_dict) or []
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

        from app.platform_utils import get_storage_provider

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
            llm = cast("BaseChatModel", cast("BaseAgent", parent_agent).llm)

        # --- 2. Memory Manager (respects memory_isolation policy) ---
        memory_manager = None
        if config.memory_isolation != MemoryIsolationPolicy.EPHEMERAL_SESSION:
            try:
                from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding

                embedding_cfg = await self._resolve_embedding_config()
                if embedding_cfg is not None:
                    memory_manager = await create_memory_manager(
                        resolve_context_binding(
                            namespaces=None,
                            agent_id=self._agent_id,
                            channel_id=None,
                            conversation_id=None,
                            task_id=None,
                            memory_policy=getattr(profile, "memory_policy", None),
                        ),
                        embedding_config=embedding_cfg,
                    )
            except Exception as e:
                logger.warning(
                    "[CustomAgentFactory] Memory manager creation failed (degraded to no-memory): %s",
                    e,
                )

        # --- 3. Max iterations ---
        max_iterations = getattr(profile, "max_iterations", None) or config.max_turns

        # --- 4. Personality style suffix ---
        from app.ai_agents.personality_templates import (
            DEFAULT_PERSONALITY_STYLE,
            PersonalityStyle,
            get_personality_template,
            is_valid_personality_style,
        )

        metadata: dict[str, object] = getattr(profile, "metadata", None) or {}
        raw_style = metadata.get("personality_style", DEFAULT_PERSONALITY_STYLE)
        personality_style = (
            cast("PersonalityStyle", raw_style)
            if isinstance(raw_style, str) and is_valid_personality_style(raw_style)
            else DEFAULT_PERSONALITY_STYLE
        )
        if personality_style != DEFAULT_PERSONALITY_STYLE:
            try:
                template = get_personality_template(personality_style)
                system_prompt += f"\n\n**Communication Style**: {template.system_prompt_suffix}"
            except Exception as e:
                logger.warning("Failed to load personality template '%s': %s", personality_style, e)

        # --- 5. Build AgentRuntimeSpec & create SkillAgent ---
        skill_ids: list[str] = getattr(profile, "skills", None) or []
        spec = AgentRuntimeSpec(
            agent_id=self._agent_id,
            name=getattr(profile, "display_name", None) or self._agent_id,
            system_prompt=system_prompt,
            skill_ids=skill_ids,
            mcp_servers=self._cached_mcp_configs,
            max_iterations=max_iterations,
        )

        enabled_builtin = getattr(profile, "enabled_builtin_tools", ())
        filtered_parent_tools = _filter_tools_by_profile(list(cast("list[BaseTool]", tools)), enabled_builtin)
        all_tools = _without_inherited_conversation_search(filtered_parent_tools)
        _append_scoped_conversation_search(
            all_tools,
            current_chat_id=_parent_chat_id(parent_agent),
            agent_id=self._agent_id,
            memory_manager=memory_manager,
        )

        storage_backend = get_storage_provider()
        agent = await create_skill_agent(
            spec=spec,
            llm=llm,
            executor=cast("BaseAgent", parent_agent).executor,
            storage_backend=storage_backend,
            skill_backend=self._cached_skill_backend,
            memory_manager=memory_manager,
            tools=all_tools,
            collect_artifacts=False,
            checkpointer=False,
        )

        logger.info(
            "[CustomAgentFactory] Built SkillAgent for '%s': skills=%d, tools=%d, memory=%s, mcp=%d",
            self._agent_id,
            len(skill_ids),
            len(all_tools),
            config.memory_isolation.value,
            len(self._cached_mcp_configs),
            extra={"complexity_tier": complexity_tier, "current_depth": current_depth},
        )
        return agent


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
        from myrm_agent_harness.api import AgentRuntimeSpec
        from myrm_agent_harness.toolkits.llms import llm_manager

        from app.platform_utils import get_storage_provider

        # 10/10 Scheme: If context is forked, we MUST drop the system_prompt entirely.
        # Otherwise, LangGraph prepends a new SystemMessage, shifting the array and breaking Prefix Cache!
        if getattr(config, "context_mode", "isolated") == "fork":
            system_prompt = ""
        else:
            system_prompt = config.system_prompt or ""

        # NOT appending task_description to system_prompt to preserve prefix cache (cache_control).

        llm = None
        if config.llm is not None:
            llm = config.llm
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
                logger.warning("[EphemeralAgentFactory] Failed to resolve model '%s': %s", config.model, e)

        if llm is None:
            llm = getattr(parent_agent, "llm", None)

        spec = AgentRuntimeSpec(
            agent_id=self._agent_id,
            name=config.display_name or self._agent_id,
            system_prompt=system_prompt,
            skill_ids=[],
            mcp_servers=[],
            max_iterations=config.max_turns,
        )

        raw_builtin = self._metadata.get("enabled_builtin_tools")
        if not isinstance(raw_builtin, (list, tuple)):
            from app.services.agent.profile_resolver import DEFAULT_ENABLED_BUILTIN_TOOLS
            raw_builtin = DEFAULT_ENABLED_BUILTIN_TOOLS
        filtered_tools = _filter_tools_by_profile(list(tools), tuple(str(x) for x in raw_builtin))

        agent = await create_skill_agent(
            spec=spec,
            llm=llm,
            executor=getattr(parent_agent, "executor", None),
            storage_backend=get_storage_provider(),
            skill_backend=None,
            memory_manager=None,
            tools=_without_inherited_conversation_search(filtered_tools),
            collect_artifacts=False,
            checkpointer=False,
        )

        logger.info(
            "[EphemeralAgentFactory] Built in-memory SkillAgent for '%s'",
            self._agent_id,
            extra={"complexity_tier": complexity_tier, "current_depth": current_depth},
        )
        return agent
