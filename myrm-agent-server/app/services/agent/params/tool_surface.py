"""[INPUT]
- app.services.agent.params.models::AgentRequest (POS: Agent API request DTO)
- app.services.agent.params.profile_apply::ProfileContext (POS: capability envelope of the turn)
- app.services.agent.params.sources::ConfigSources (POS: search / retrieval / MCP sources)
- app.services.agent.profile.profile_resolver::resolve_builtin_tool_flags (POS: builtin tool flag mapping)
- app.services.agent.tool_mount (POS: entry-surface meta tool mount policy)
- app.core.channel_bridge.config_loader::load_user_configs (POS: decrypted user config loader)

[OUTPUT]
- ToolSurface: builtin tool flags, prompt mode, search depth for this entry surface
- resolve_tool_surface(): pick the fast-search surface or the general web-chat surface

[POS]
Entry-surface stage of Agent request conversion. Fast mode is the only surface without file/bash:
it forces an answer_tool-only profile and wipes skills / MCP / subagents / media generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, MemoryWritePolicy

from .models import AgentRequest
from .profile_apply import ProfileContext
from .sources import ConfigSources

if TYPE_CHECKING:
    from app.services.agent.profile.profile_resolver import BuiltinToolFlags

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolSurface:
    """Tool mount decision for the entry surface that runs this turn."""

    is_fast: bool
    tool_flags: BuiltinToolFlags
    prompt_mode: str
    search_depth: str = "normal"


async def resolve_tool_surface(request: AgentRequest, profile: ProfileContext, sources: ConfigSources) -> ToolSurface:
    """Mount the fast-search surface or the general web-chat surface.

    Fast mode intentionally overwrites the profile (tools, skills, MCP, subagents, media, memory
    policy) — the saved Agent profile does not apply to a one-shot answer run. A search config
    reloaded here is written back into ``sources`` because that is the value the mount reads.
    """

    from app.services.agent.profile.profile_resolver import resolve_builtin_tool_flags
    from app.services.agent.tool_mount import ExecutionSurface, resolve_agent_mount

    if request.action_mode == "fast":
        search_depth = request.search_depth if request.search_depth in ("normal", "deep") else "normal"
        # SHPOIB E2E seeds searchServices on the private API immediately before kickoff;
        # bypass stale config-cache reads so web_search_tool mounts on the same turn.
        if sources.search_cfg is None:
            from app.core.channel_bridge.config_cache import (
                invalidate_user_configs_cache,
            )
            from app.core.channel_bridge.config_loader import (
                load_user_configs as reload_user_configs,
            )

            invalidate_user_configs_cache()
            refreshed_configs = await reload_user_configs()
            if refreshed_configs is not None and refreshed_configs.search_cfg is not None:
                sources.search_cfg = refreshed_configs.search_cfg
        # Deep vs normal differs by search_depth (sufficiency, prompt suffix, limits),
        # not browser — deep workflow is web_search → web_fetch → answer self-review.
        fast_builtin: list[str] = ["answer_tool"]
        tool_flags = resolve_agent_mount(
            ExecutionSurface.WEB_FAST,
            resolve_builtin_tool_flags(fast_builtin, allow_answer_tool=True),
        )
        prompt_mode = "search"
        sources.search_available = sources.search_cfg is not None
        if not sources.search_available:
            logger.warning(
                "Fast search requested without resolved search_service_cfg; chat_id=%s",
                request.chat_id,
            )
        profile.user_instructions = request.user_instructions
        profile.agent_skill_ids = []
        profile.agent_skill_configs = None
        profile.mcp_configs = None
        profile.agent_subagent_ids = None
        profile.openapi_services = None
        profile.agent_max_iterations = 50 if search_depth == "deep" else 30
        profile.engine_params = {"max_tool_calls": 20 if search_depth == "deep" else 8}
        profile.agent_memory_policy = AgentMemoryPolicy(write_policy=MemoryWritePolicy.CONVERSATION)
        return ToolSurface(is_fast=True, tool_flags=tool_flags, prompt_mode=prompt_mode, search_depth=search_depth)

    if sources.search_cfg is None and "web_search" in profile.enabled_builtin_tools:
        from app.core.channel_bridge.config_cache import (
            invalidate_user_configs_cache,
        )
        from app.core.channel_bridge.config_loader import (
            load_user_configs as reload_user_configs,
        )

        invalidate_user_configs_cache()
        refreshed_configs = await reload_user_configs()
        if refreshed_configs is not None and refreshed_configs.search_cfg is not None:
            sources.search_cfg = refreshed_configs.search_cfg
            sources.search_is_user_configured = bool(refreshed_configs.search_is_user_configured)

    if sources.search_cfg is not None and "web_search" in profile.enabled_builtin_tools:
        sources.search_available = True

    tool_flags = resolve_agent_mount(
        ExecutionSurface.WEB_CHAT,
        resolve_builtin_tool_flags(profile.enabled_builtin_tools),
    )
    prompt_mode = profile.resolved.prompt_mode if profile.resolved else "full"
    return ToolSurface(is_fast=False, tool_flags=tool_flags, prompt_mode=prompt_mode)
