"""Assembly steps shared by the factories that build a delegated sub-agent's SkillAgent.

[INPUT]
- myrm_agent_harness.core.security.tool_registry::TOOL_TO_GROUP (POS: the capability group a built-in tool belongs to)
- myrm_agent_harness.toolkits::create_memory_tools (POS: builds the memory tools bound to one memory manager)
- app.core.agent.tool_description_locale::resolve_tool_description_locale (POS: locale a tool description is rendered in)
- app.core.skills.creation (POS: the skill creation service a write backend persists through)

[OUTPUT]
- filter_tools_by_profile: the inherited parent tools the sub-agent's enabled built-in groups allow
- inherit_parent_security_config: the parent's SecurityConfig, so the child keeps the parent's security posture
- rebind_subagent_memory_search_tool / apply_subagent_memory_search_rebind: the child's memory_search_tool searches only its own memory
- subagent_write_backend: the skill write backend, mounted only when the sub-agent may manage skills

[POS]
Shared by CustomAgentFactory (database profile) and EphemeralAgentFactory (in-memory blueprint), so a delegated
sub-agent of either kind gets the same tool boundary, security posture and memory scope.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.security.types import SecurityConfig
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig
    from myrm_agent_harness.backends.skills.creation_protocols import SkillWriteBackend

logger = logging.getLogger(__name__)


def filter_tools_by_profile(tools: list[BaseTool], enabled_builtin_tools: tuple[str, ...]) -> list[BaseTool]:
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


def inherit_parent_security_config(parent_agent: object) -> SecurityConfig | None:
    """Inherit the parent agent's SecurityConfig for the child SkillAgent.

    Mirrors the framework's bare-BaseAgent child path (builder.build_child_agent)
    so delegated SkillAgents share the same security posture (approval policies,
    capabilities, path policy) as the parent. Returns None when the parent has no
    runtime config (e.g. SimpleNamespace in unit tests) so callers fall back to
    framework fail-closed defaults.
    """
    config = getattr(parent_agent, "config", None)
    if config is None:
        return None
    security_config = getattr(config, "security_config", None)
    if security_config is None:
        logger.warning("[subagent] parent_agent.config.security_config is None — child will fall back to fail-closed defaults")
    return security_config


def rebind_subagent_memory_search_tool(
    tools: list[BaseTool],
    *,
    memory_manager: object,
    description_locale: str | None = None,
) -> None:
    """Replace the inherited memory_search_tool with one that searches only the subagent's own memory.

    The parent's tool may carry its wiki and past-conversation corpora; a delegated subagent never inherits them.
    """
    from myrm_agent_harness.toolkits import create_memory_tools
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

    if not isinstance(memory_manager, MemoryManager):
        return

    rebuilt = create_memory_tools(memory_manager, description_locale=description_locale)
    rebuilt_search = next(
        (tool for tool in rebuilt if getattr(tool, "name", "") == "memory_search_tool"),
        None,
    )
    if rebuilt_search is None:
        return

    for index, tool in enumerate(tools):
        if getattr(tool, "name", "") == "memory_search_tool":
            tools[index] = rebuilt_search
            return


def apply_subagent_memory_search_rebind(
    tools: list[BaseTool],
    *,
    parent_agent: object,
    memory_manager: object | None,
    enabled_builtin: tuple[str, ...],
) -> None:
    """Rebind inherited memory_search_tool when the subagent profile enables memory."""
    if memory_manager is None or "memory" not in enabled_builtin:
        return
    from app.core.agent.tool_description_locale import resolve_tool_description_locale

    tool_description_locale = resolve_tool_description_locale(
        agent_locale=getattr(parent_agent, "locale", None),
        channel=getattr(parent_agent, "channel_name", None),
    )
    rebind_subagent_memory_search_tool(
        tools,
        memory_manager=memory_manager,
        description_locale=tool_description_locale,
    )


def subagent_write_backend(config: SubagentConfig) -> SkillWriteBackend | None:
    """Mount skill_manage_tool when the subagent allowlist includes it."""
    if "skill_manage_tool" not in config.tools:
        return None
    from app.core.skills.creation.service import skill_creation_service
    from app.core.skills.creation.version_persisting_backend import (
        VersionPersistingSkillWriteBackend,
    )

    return VersionPersistingSkillWriteBackend(skill_creation_service)
