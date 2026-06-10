"""Unified Agent profile resolution with TTL caching.

All entry points (Web, Channel, Cron, Kanban, Eval, Voice) share this single
resolver, ensuring consistent field coverage and cache invalidation.

[INPUT]
services.agent.agent_service::AgentService (POS: 业务层 Agent 服务)
core.memory.adapters.policy::memory_policy_from_dict (POS: 记忆策略字典解析)

[OUTPUT]
DEFAULT_ENABLED_BUILTIN_TOOLS: 所有入口共享的默认启用工具集合
BuiltinToolFlags: 工具启用标志 TypedDict
resolve_builtin_tool_flags: enabled_builtin_tools → enable_xxx flags 统一映射
ResolvedAgentProfile: 统一的智能体配置解析结果（含 auto_restore_domains 等运行时字段）
AgentProfileResolver: 全局单例解析器（带 TTL 缓存）
get_agent_profile_resolver: 获取全局单例

[POS]
统一智能体配置解析服务。消除 Web/Channel/Cron/Kanban/Eval/Voice 入口的重复解析逻辑，
提供带 TTL 缓存的单点解析，确保字段完整性和缓存一致性。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Sequence, TypedDict

from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy

logger = logging.getLogger(__name__)


DEFAULT_ENABLED_BUILTIN_TOOLS: tuple[str, ...] = ("web_search", "memory")
"""Canonical default for enabled_builtin_tools across all entry points."""


class BuiltinToolFlags(TypedDict):
    """Boolean flags derived from enabled_builtin_tools for GeneralAgentParams."""

    enable_browser: bool
    enable_computer_use: bool
    enable_file_ops: bool
    enable_code_execute: bool
    enable_wiki: bool
    enable_kanban: bool
    enable_llm_map: bool
    enable_answer_tool: bool


def resolve_builtin_tool_flags(
    tools: Sequence[str],
) -> BuiltinToolFlags:
    """Map enabled_builtin_tools list to GeneralAgentParams boolean flags.

    All entry points (Web, Channel, Cron, Kanban, Eval, Voice) must use this
    function to ensure parity. Adding a new tool flag requires only a single
    change here.
    """
    return BuiltinToolFlags(
        enable_browser="browser" in tools,
        enable_computer_use="computer_use" in tools,
        enable_file_ops="file_ops" in tools,
        enable_code_execute="code_execute" in tools,
        enable_wiki="wiki" in tools,
        enable_kanban="kanban" in tools,
        enable_llm_map="llm_map" in tools,
        enable_answer_tool="answer_tool" in tools,
    )


def _coerce_str_tuple(val: object) -> tuple[str, ...]:
    """Normalize metadata list/tuple/scalar values into a tuple of strings."""
    if val is None:
        return ()
    if isinstance(val, str):
        return (val,)
    if isinstance(val, (list, tuple)):
        return tuple(str(x) for x in val)
    return (str(val),)


def _coerce_tool_selections(val: object) -> dict[str, tuple[str, ...]]:
    """Normalize metadata ``mcp_tool_selections`` into {server: (tool, ...)}.

    Delegates to ``mcp_selection.coerce_tool_selections`` (canonical impl).
    Returns ``{}`` instead of ``None`` for dataclass default compatibility.
    """
    from app.services.agent.params.mcp_selection import coerce_tool_selections

    return coerce_tool_selections(val) or {}


_CACHE_TTL_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class ResolvedAgentProfile:
    """Unified agent profile resolved from database.

    Contains all fields needed by GeneralAgentParams across Web/Channel/Cron.
    """

    agent_id: str
    skill_ids: tuple[str, ...]
    mcp_ids: tuple[str, ...]
    enabled_builtin_tools: tuple[str, ...]
    agent_type: str = "individual"
    system_prompt: str | None = None
    model: str | None = None
    subagent_ids: tuple[str, ...] | None = None
    security_overrides: dict[str, object] | None = None
    personality_style: str | None = None
    prompt_mode: str = "full"
    max_iterations: int | None = None
    workspace_policy: str | None = None
    memory_policy: AgentMemoryPolicy | None = None
    memory_decay_profile: str | None = None
    skill_configs: dict[str, dict] | None = field(default=None, kw_only=True)
    engine_params: dict[str, object] | None = field(default=None, kw_only=True)
    auto_restore_domains: tuple[str, ...] = field(default_factory=tuple, kw_only=True)
    model_kwargs: dict[str, object] | None = field(default=None, kw_only=True)
    openapi_services: list[dict[str, object]] = field(default_factory=list, kw_only=True)
    session_policy: dict[str, object] | None = field(default=None, kw_only=True)
    mcp_tool_selections: dict[str, tuple[str, ...]] = field(default_factory=dict, kw_only=True)
    """Per-MCP-server tool whitelist {server: (tool, ...)}; empty = no per-tool constraint."""
    browser_engine: str | None = field(default=None, kw_only=True)
    browser_source: str | None = field(default=None, kw_only=True)
    dialog_policy: str | None = field(default=None, kw_only=True)
    session_recording: str | None = field(default=None, kw_only=True)

    notify_targets: tuple[dict[str, str], ...] = field(default_factory=tuple, kw_only=True)
    """Configured notification targets: each dict has {channel, recipient_id, label?}."""

    tool_gateway_config: dict[str, object] | None = field(default=None, kw_only=True)
    """Tool Gateway configuration for third-party tools."""

    built_in: bool = field(default=False, kw_only=True)
    """Whether this is a built-in (system preset) profile."""


class AgentProfileResolver:
    """Resolves agent profiles from database with TTL caching.

    Thread-safe for asyncio: cache is a plain dict (single-threaded event loop).
    TTL default: 5 minutes — matches the previous channel-layer cache behavior.
    """

    __slots__ = ("_cache",)

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, ResolvedAgentProfile | None]] = {}

    async def resolve(self, agent_id: str) -> ResolvedAgentProfile | None:
        """Resolve agent profile by ID. Returns None if not found."""
        cache_key = agent_id
        now = time.monotonic()

        cached = self._cache.get(cache_key)
        if cached is not None:
            ts, profile = cached
            if now - ts < _CACHE_TTL_SECONDS:
                return profile

        profile = await self._load_from_db(agent_id)
        self._cache[cache_key] = (now, profile)
        return profile

    def invalidate(self, agent_id: str) -> None:
        """Remove cache entry for the given agent_id."""
        if agent_id in self._cache:
            del self._cache[agent_id]

    @staticmethod
    async def _load_from_db(agent_id: str) -> ResolvedAgentProfile | None:
        """Load agent profile from database via AgentService."""
        try:
            from app.platform_utils import get_session_factory
            from app.services.agent.agent_service import AgentService

            session_factory = get_session_factory()
            async with session_factory() as _db:
                agent = await AgentService.get_agent_by_id(agent_id)
                if not agent:
                    logger.warning("Agent '%s' not found", agent_id)
                    return None

                metadata: dict[str, object] = agent.metadata or {}

                raw_subagent_ids = metadata.get("subagent_ids")
                raw_mcp_ids = metadata.get("mcp_ids", [])
                raw_security = metadata.get("security_overrides")
                raw_personality = metadata.get("personality_style")
                raw_builtin_tools = metadata.get("enabled_builtin_tools", list(DEFAULT_ENABLED_BUILTIN_TOOLS))
                raw_workspace_policy = metadata.get("workspace_policy")
                raw_engine_params = metadata.get("engine_params")

                mcp_tuple = _coerce_str_tuple(raw_mcp_ids)
                mcp_tool_selections = _coerce_tool_selections(metadata.get("mcp_tool_selections"))
                sub_tuple = _coerce_str_tuple(raw_subagent_ids) if raw_subagent_ids is not None else ()
                tools_tuple = (
                    _coerce_str_tuple(raw_builtin_tools) if raw_builtin_tools is not None else DEFAULT_ENABLED_BUILTIN_TOOLS
                )
                raw_auto_restore = metadata.get("auto_restore_domains")
                auto_domains_tuple = _coerce_str_tuple(raw_auto_restore) if raw_auto_restore is not None else ()

                raw_browser_engine = getattr(agent, "browser_engine", None) or metadata.get("browser_engine")
                browser_engine = str(raw_browser_engine) if raw_browser_engine else None
                raw_browser_source = getattr(agent, "browser_source", None) or metadata.get("browser_source")
                browser_source = str(raw_browser_source) if raw_browser_source else None
                raw_dialog_policy = getattr(agent, "dialog_policy", None) or metadata.get("dialog_policy")
                dialog_policy = str(raw_dialog_policy) if raw_dialog_policy else None
                raw_session_recording = getattr(agent, "session_recording", None) or metadata.get("session_recording")
                session_recording = str(raw_session_recording) if raw_session_recording else None

                raw_model_selection = getattr(agent, "model_selection", None)
                model_kwargs: dict[str, object] | None = None
                if isinstance(raw_model_selection, dict):
                    raw_kwargs = raw_model_selection.get("modelKwargs")
                    if isinstance(raw_kwargs, dict):
                        model_kwargs = raw_kwargs

                raw_openapi_services = metadata.get("openapi_services", [])
                openapi_services: list[dict[str, object]] = (
                    list(raw_openapi_services) if isinstance(raw_openapi_services, list) else []
                )

                raw_notify = metadata.get("notify_targets", [])
                notify_targets: tuple[dict[str, str], ...] = tuple(
                    d
                    for d in (raw_notify if isinstance(raw_notify, list) else [])
                    if isinstance(d, dict) and "channel" in d and "recipient_id" in d
                )

                raw_agent_type = metadata.get("agent_type", "individual")

                return ResolvedAgentProfile(
                    agent_id=agent_id,
                    agent_type=str(raw_agent_type) if raw_agent_type else "individual",
                    system_prompt=agent.system_prompt,
                    model=agent.model,
                    skill_ids=tuple(agent.skills or []),
                    skill_configs=agent.skill_configs,
                    subagent_ids=sub_tuple if sub_tuple else None,
                    mcp_ids=mcp_tuple,
                    mcp_tool_selections=mcp_tool_selections,
                    browser_engine=browser_engine,
                    browser_source=browser_source,
                    dialog_policy=dialog_policy,
                    session_recording=session_recording,
                    security_overrides=(raw_security if isinstance(raw_security, dict) else None),
                    personality_style=str(raw_personality) if raw_personality else None,
                    prompt_mode=str(metadata.get("prompt_mode", "full")),
                    max_iterations=agent.max_iterations,
                    workspace_policy=(str(raw_workspace_policy) if raw_workspace_policy else None),
                    memory_policy=(agent.memory_policy if isinstance(agent.memory_policy, AgentMemoryPolicy) else None),
                    memory_decay_profile=getattr(agent, "memory_decay_profile", None),
                    enabled_builtin_tools=tools_tuple,
                    model_kwargs=model_kwargs,
                    openapi_services=openapi_services,
                    auto_restore_domains=auto_domains_tuple,
                    engine_params=(raw_engine_params if isinstance(raw_engine_params, dict) else None),
                    session_policy=(metadata.get("session_policy") if isinstance(metadata.get("session_policy"), dict) else None),
                    notify_targets=notify_targets,
                    tool_gateway_config=(
                        metadata.get("tool_gateway_config") if isinstance(metadata.get("tool_gateway_config"), dict) else None
                    ),
                    built_in=bool(getattr(agent, "is_built_in", False) or getattr(agent, "is_public", False)),
                )
        except Exception:
            logger.error("Failed to resolve agent profile for '%s'", agent_id, exc_info=True)
            return None


_resolver_instance: AgentProfileResolver | None = None


def get_agent_profile_resolver() -> AgentProfileResolver:
    """Return the global AgentProfileResolver singleton."""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = AgentProfileResolver()
    return _resolver_instance
