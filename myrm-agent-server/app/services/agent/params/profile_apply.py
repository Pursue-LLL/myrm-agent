"""[INPUT]
- app.services.agent.params.models::AgentRequest (POS: Agent API request DTO)
- app.services.agent.profile.profile_resolver::ResolvedAgentProfile (POS: saved Agent profile)
- app.services.agent.params.mcp_selection (POS: per-agent MCP server/tool filtering)
- app.services.agent.params.profile_output_suffixes (POS: personality + response-locale suffix injection)
- app.ai_agents.team_protocol::build_leader_protocol_prompt (POS: team leader protocol prompt)
- app.platform_utils.sandbox.tool_gateway::merge_tool_gateway_config (POS: tool gateway config merge)
- app.core.types::MCPServerConfig (POS: MCP server config DTO)

[OUTPUT]
- ProfileContext: instructions, tool entitlements, MCP servers, skills/subagents, limits, memory policy, gateway config
- apply_agent_profile(): merge the saved Agent profile with the per-request configuration

[POS]
Agent profile stage of Agent request conversion. Turns "which agent is this" into the capability
envelope of the turn; the request-level ``agent_config`` wins over the saved profile.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy

from app.core.types import MCPServerConfig

from .model_plan import ModelPlan, ModelResolver
from .models import AgentRequest

if TYPE_CHECKING:
    from app.services.agent.profile.profile_resolver import ResolvedAgentProfile

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProfileContext:
    """Capability envelope resolved from the saved Agent profile and the request."""

    resolved: ResolvedAgentProfile | None = None
    user_instructions: str | None = None
    enabled_builtin_tools: list[str] = field(default_factory=list)
    auto_restore_domains: list[str] = field(default_factory=list)
    browser_source: str | None = None
    dialog_policy: str | None = None
    session_recording: str | None = None
    kanban_default_board_id: str | None = None
    mcp_configs: list[MCPServerConfig] | None = None
    agent_skill_ids: list[str] = field(default_factory=list)
    agent_skill_configs: dict[str, dict] | None = None
    agent_subagent_ids: list[str] | None = None
    agent_security_raw: dict[str, object] | None = None
    agent_max_iterations: int | None = None
    agent_memory_policy: AgentMemoryPolicy | None = None
    agent_memory_decay_profile: str | None = None
    agent_memory_extraction_preset: str | None = None
    engine_params: dict[str, object] | None = None
    openapi_services: list[dict[str, object]] | None = None
    tool_gateway_config: dict[str, object] | None = None


async def apply_agent_profile(
    request: AgentRequest,
    plan: ModelPlan,
    providers_dict: dict[str, object] | None,
    mcp_configs: list[MCPServerConfig] | None,
    *,
    resolve: ModelResolver,
) -> ProfileContext:
    """Resolve the Agent profile, merge the request overrides, return the capability envelope.

    A profile with its own model replaces ``plan.model_cfg`` when the request carries no explicit
    selection: the model belongs to the profile's contract, not to the user-facing model slots.
    """

    from app.services.agent.profile.profile_resolver import (
        DEFAULT_ENABLED_BUILTIN_TOOLS,
        get_agent_profile_resolver,
    )

    profile = ProfileContext(
        user_instructions=request.user_instructions,
        enabled_builtin_tools=list(DEFAULT_ENABLED_BUILTIN_TOOLS),
        mcp_configs=mcp_configs,
    )

    if request.agent_id:
        resolved = await get_agent_profile_resolver().resolve(request.agent_id)
        profile.resolved = resolved
        if resolved:
            if not request.agent_config and resolved.system_prompt:
                profile.user_instructions = (
                    f"{profile.user_instructions}\n\n{resolved.system_prompt}"
                    if profile.user_instructions
                    else resolved.system_prompt
                )
            # Inject Hybrid Routing Rules when browser + desktop control are both runtime-ready
            if (
                resolved.enabled_builtin_tools
                and "browser" in resolved.enabled_builtin_tools
                and "computer_use" in resolved.enabled_builtin_tools
            ):
                from app.config.computer_use_deploy import (
                    is_computer_use_deploy_supported,
                )

                hybrid_ready = is_computer_use_deploy_supported()
            else:
                hybrid_ready = False

            if hybrid_ready:
                hybrid_routing_rule = (
                    "\n\n[HYBRID EXECUTION ROUTING RULES]\n"
                    "You have both 'browser' and 'computer_use' (desktop) tools available. You MUST follow these strict routing rules:\n"
                    "1. For ANY web page interaction (clicking links, filling forms, reading web content), you MUST use 'browser_snapshot' and 'browser_interact_tool'. It is 10x faster and more reliable.\n"
                    "2. DO NOT use 'desktop_snapshot' or 'desktop_interact_tool' to interact with web pages.\n"
                    "3. ONLY use 'desktop_snapshot' and 'desktop_interact_tool' when dealing with native OS dialogs (e.g., File Upload/Save dialogs, OS permission prompts) or browser extensions that 'browser_interact_tool' cannot see.\n"
                    "4. If 'browser_snapshot' or 'browser_interact_tool' warns you that an OS dialog is blocking the page, immediately switch to 'desktop_snapshot' and 'desktop_interact_tool'."
                )
                profile.user_instructions = (
                    f"{profile.user_instructions}{hybrid_routing_rule}"
                    if profile.user_instructions
                    else hybrid_routing_rule.strip()
                )

            profile.agent_skill_ids = list(resolved.skill_ids)
            profile.agent_skill_configs = resolved.skill_configs
            profile.agent_subagent_ids = list(resolved.subagent_ids) if resolved.subagent_ids else None
            profile.agent_security_raw = resolved.security_overrides
            profile.enabled_builtin_tools = list(resolved.enabled_builtin_tools)
            profile.agent_max_iterations = resolved.max_iterations
            profile.agent_memory_policy = resolved.memory_policy
            profile.agent_memory_decay_profile = resolved.memory_decay_profile
            profile.agent_memory_extraction_preset = resolved.memory_extraction_preset
            profile.engine_params = resolved.engine_params
            profile.auto_restore_domains = list(resolved.auto_restore_domains)
            profile.browser_source = resolved.browser_source
            profile.dialog_policy = resolved.dialog_policy
            profile.session_recording = resolved.session_recording
            profile.openapi_services = resolved.openapi_services or None

            # Safety net: use agent's model when frontend didn't pass model_selection
            if not request.model_selection and resolved.model:
                if resolved.model_kwargs:
                    from app.services.agent.params.models import ModelSelection

                    agent_model_selection = ModelSelection(
                        provider_id="auto",
                        model=resolved.model,
                        model_kwargs=resolved.model_kwargs,
                    )
                    try:
                        plan.model_cfg = await resolve(agent_model_selection, providers_dict)
                    except Exception:
                        logger.warning(
                            "Failed to resolve agent model '%s' with kwargs, keeping default",
                            resolved.model,
                        )
                else:
                    from app.core.channel_bridge.model_resolver import (
                        resolve_model_config as _resolve_override_model,
                    )

                    try:
                        plan.model_cfg = _resolve_override_model(providers_dict, model_override=resolved.model)
                    except Exception:
                        logger.warning(
                            "Failed to resolve agent model '%s', keeping default",
                            resolved.model,
                        )

            if resolved.agent_type == "team":
                from app.ai_agents.team_protocol import build_leader_protocol_prompt

                leader_protocol = await build_leader_protocol_prompt(
                    profile.agent_subagent_ids or [],
                    leader_id=request.agent_id,
                    dynamic_discovery=True,
                )
                profile.user_instructions = (
                    f"{profile.user_instructions}\n\n{leader_protocol}" if profile.user_instructions else leader_protocol
                )

            from app.services.agent.params.profile_output_suffixes import (
                apply_profile_output_suffixes,
            )

            suffix_engine_params: dict[str, object] | None = dict(resolved.engine_params) if resolved.engine_params else None
            if request.engine_params:
                if suffix_engine_params:
                    suffix_engine_params = {
                        **suffix_engine_params,
                        **request.engine_params,
                    }
                else:
                    suffix_engine_params = dict(request.engine_params)

            profile.user_instructions = apply_profile_output_suffixes(
                profile.user_instructions,
                personality_style=resolved.personality_style,
                engine_params=suffix_engine_params,
                agent_id=request.agent_id,
            )

    resolved = profile.resolved
    if profile.mcp_configs and resolved:
        from app.services.agent.params.mcp_selection import apply_agent_mcp_selection

        profile.mcp_configs = (
            apply_agent_mcp_selection(
                profile.mcp_configs,
                mcp_ids=resolved.mcp_ids or None,
                mcp_tool_selections=resolved.mcp_tool_selections or None,
            )
            or None
        )

    if request.engine_params:
        if profile.engine_params:
            profile.engine_params = {**profile.engine_params, **request.engine_params}
        else:
            profile.engine_params = dict(request.engine_params)

    if request.agent_config:
        cfg = request.agent_config
        profile.agent_skill_ids = cfg.skill_ids
        if getattr(cfg, "skill_configs", None) is not None:
            profile.agent_skill_configs = cfg.skill_configs
        profile.enabled_builtin_tools = cfg.enabled_builtin_tools
        profile.auto_restore_domains = list(cfg.auto_restore_domains)
        profile.browser_source = (
            cfg.browser_source if hasattr(cfg, "browser_source") else (resolved.browser_source if resolved else None)
        )
        profile.dialog_policy = (
            cfg.dialog_policy if hasattr(cfg, "dialog_policy") else (resolved.dialog_policy if resolved else None)
        )
        profile.session_recording = (
            cfg.session_recording if hasattr(cfg, "session_recording") else (resolved.session_recording if resolved else None)
        )
        profile.kanban_default_board_id = cfg.kanban_default_board_id if hasattr(cfg, "kanban_default_board_id") else None
        if (gateway_cfg := getattr(cfg, "tool_gateway_config", None)) is not None:
            tool_gateway_config: dict[str, object] | None = gateway_cfg.model_dump(mode="json")
        else:
            tool_gateway_config = resolved.tool_gateway_config if resolved else None
    else:
        profile.dialog_policy = resolved.dialog_policy if resolved else None
        profile.session_recording = resolved.session_recording if resolved else None
        tool_gateway_config = resolved.tool_gateway_config if resolved else None

    if tool_gateway_config and isinstance(tool_gateway_config, dict):
        if tool_gateway_config.get("use_gateway") and not tool_gateway_config.get("auth_token"):
            logger.warning("tool_gateway_config.use_gateway is true but auth_token is missing; disabling gateway routing")
            tool_gateway_config["use_gateway"] = False

    from app.platform_utils.sandbox.tool_gateway import merge_tool_gateway_config

    profile.tool_gateway_config = merge_tool_gateway_config(
        tool_gateway_config if isinstance(tool_gateway_config, dict) else None
    )

    return profile
