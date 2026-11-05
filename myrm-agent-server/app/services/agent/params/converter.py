"""[INPUT]
- app.ai_agents::GeneralAgentParams (POS: General Agent runtime parameter DTO)
- app.services.agent.params.conversion (POS: conversion stages — model plan, sources, profile, chat context, tool surface)
- app.services.agent.params.routing (POS: specialty / complexity / retry-floor routing + cross-turn routing memory)
- app.services.agent.params.query_enrichment (POS: server-side query context blocks)

[OUTPUT]
- convert_to_general_agent_params(): build runtime params and routing metadata for GeneralAgent
- prevalidate_archive_restore_actions(): validate explicit archive restore actions before request persistence

[POS]
Agent request parameter conversion layer. Orchestrates the conversion stages in a fixed order —
model plan, routing, config sources, agent profile, model finalization, query enrichment, tool
surface — then assembles `GeneralAgentParams`. Fast mode (`action_mode='fast'`) overrides builtin
tools to answer_tool-only plus forced web search; deep search uses web_fetch + sufficiency, not
browser eager bind.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import Request

from app.ai_agents import GeneralAgentParams
from app.core.security.privacy_settings import resolve_privacy_params
from app.core.security.session_overlay import SecurityOverlaySpec
from app.core.types import ChatHistoryReq
from app.services.agent.moa_preset_resolver import (
    apply_moa_preset_activation,
    resolve_effective_moa_preset_id,
)
from app.services.agent.resolve_enable_web_fetch import resolve_enable_web_fetch

from .archive_restore import (
    ArchiveRestoreRequestError,
    prevalidate_archive_restore_actions,
)
from .conversion import (
    apply_agent_profile,
    finalize_model_plan,
    resolve_chat_context,
    resolve_config_sources,
    resolve_model_plan,
    resolve_tool_surface,
)
from .helpers import _declared_capabilities, _extract_code_execution_network, _requested_privacy_params
from .media import _extract_media_generation_params
from .models import AgentRequest
from .query_enrichment import enrich_query
from .resolvers import _resolve_model_config
from .routing import resolve_routing_outcome

logger = logging.getLogger(__name__)

type ReasoningDisplayMode = Literal["off", "collapsed", "inline"]
_REASONING_DISPLAY_MODES: tuple[ReasoningDisplayMode, ...] = ("off", "collapsed", "inline")


__all__ = [
    "ArchiveRestoreRequestError",
    "convert_to_general_agent_params",
    "prevalidate_archive_restore_actions",
]


async def convert_to_general_agent_params(
    request: AgentRequest,
    chat_history: ChatHistoryReq,
    http_request: Request | None = None,
) -> tuple[
    GeneralAgentParams,
    str | None,
    str | None,
    str | None,
    list[str],
    list[dict[str, object]],
]:
    """将 Agent API 请求转换为 General Agent 参数。

    从 DB 读取用户配置（已解密），解析 API Key 和检索模型配置。
    chat_history 由调用方从 DB 加载后传入。

    Returns:
        Tuple of (GeneralAgentParams, routing_tier or None, routing_specialty or None,
        routing_reason or None, context_reference_warnings, archive_restore_results)
    """

    from app.core.channel_bridge.config_loader import load_user_configs

    configs = await load_user_configs()
    providers_dict = configs.providers_dict if configs else None

    plan = await resolve_model_plan(request, configs, providers_dict, resolve=_resolve_model_config)
    routing = await resolve_routing_outcome(request, plan, providers_dict, resolve=_resolve_model_config)

    sources = await resolve_config_sources(request, configs)
    profile = await apply_agent_profile(
        request,
        plan,
        providers_dict,
        sources.mcp_configs,
        resolve=_resolve_model_config,
    )
    finalize_model_plan(request, plan, providers_dict)

    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    GeneralAgentParams.model_rebuild(
        _types_namespace={
            "EmbeddingConfig": EmbeddingConfig,
            "RerankerConfig": RerankerConfig,
        }
    )

    security_config_dict = configs.security_config_dict if configs else None
    request_state = http_request.state if http_request is not None else None
    security_overlay = SecurityOverlaySpec(
        preset=request.security_preset,
        trust_zone=getattr(request_state, "trust_zone", None),
        admission_path=getattr(request_state, "admission_path", None),
    )

    external_agents_config = None
    if configs and configs.external_agents_dict:
        agents_list = configs.external_agents_dict.get("agents")
        if isinstance(agents_list, list):
            external_agents_config = agents_list

    ps_dict = configs.personal_settings_dict if configs else None
    voice_dict = configs.voice_dict if configs else None
    image_gen_params, video_gen_params, tts_params = _extract_media_generation_params(
        ps_dict, providers_dict, profile.enabled_builtin_tools, voice_dict
    )

    code_exec_allow_network = _extract_code_execution_network(ps_dict)

    from app.core.agent.tool_description_locale import resolve_agent_params_locale

    locale = resolve_agent_params_locale(
        explicit=request.locale,
        personal_settings=ps_dict if isinstance(ps_dict, dict) else None,
        channel="web_chat",
    )

    reasoning_display_mode: ReasoningDisplayMode | None = request.reasoning_display_mode
    if reasoning_display_mode is None and isinstance(ps_dict, dict):
        raw_mode = ps_dict.get("reasoningDisplayMode")
        if isinstance(raw_mode, str):
            reasoning_display_mode = next((m for m in _REASONING_DISPLAY_MODES if m == raw_mode.strip().lower()), None)
    if reasoning_display_mode is None:
        reasoning_display_mode = "collapsed"

    context = await resolve_chat_context(request)

    privacy_routing_obj: dict[str, object] | None = None
    if request.privacy_routing is not None:
        privacy_routing_obj = {str(k): v for k, v in request.privacy_routing.items()}

    privacy_params = resolve_privacy_params(ps_dict, _requested_privacy_params(request))

    enriched = await enrich_query(request, context, plan.model_cfg)
    final_query = enriched.query

    from app.core.channel_bridge.learn_handler import learn_authoring_prompt_text

    security_overlay = security_overlay.model_copy(
        update={
            "learn_authoring": learn_authoring_prompt_text(final_query) is not None,
        }
    )
    security_config_dict = security_overlay.apply(security_config_dict)

    declared_caps = _declared_capabilities(security_config_dict, profile.agent_security_raw)

    surface = await resolve_tool_surface(request, profile, sources)

    if request.regenerate_instruction:
        regen_suffix = f"\n\n[Regeneration guidance: {request.regenerate_instruction}]"
        profile.user_instructions = (
            f"{profile.user_instructions}{regen_suffix}" if profile.user_instructions else regen_suffix.strip()
        )

    # Every Wiki surface (tools, long-reply auto-archive, post-compaction archive) keys off this
    # flag, so every Wiki writer inherits the incognito gate from this one place.
    if request.incognito_mode:
        surface.tool_flags["enable_wiki"] = False

    from app.config.settings import get_settings
    from app.services.agent.profile.profile_resolver import is_sandbox_capable_tools

    sandbox_capable = is_sandbox_capable_tools(
        profile.enabled_builtin_tools,
        declared_capabilities=declared_caps,
    )

    params = GeneralAgentParams(
        message_id=request.message_id,
        chat_id=request.chat_id,
        agent_id=request.agent_id,
        project_id=context.project_id,
        query=final_query,
        chat_history=chat_history,
        model_cfg=plan.model_cfg,
        fallback_model_cfg=plan.fallback_model_cfg,
        fallback_model_cfgs=plan.fallback_model_cfgs,
        safety_fallback_model_cfg=plan.safety_fallback_model_cfg,
        lite_model_cfg=plan.lite_model_cfg,
        fallback_lite_model_cfg=plan.fallback_lite_model_cfg,
        fallback_lite_model_cfgs=plan.fallback_lite_model_cfgs,
        vision_fallback_model_cfg=plan.vision_fallback_model_cfg,
        vision_fallback_model_cfgs=plan.vision_fallback_model_cfgs,
        video_fallback_model_cfgs=plan.video_fallback_model_cfgs,
        search_service_cfg=sources.search_cfg,
        mcp_cfg=profile.mcp_configs,
        user_instructions=profile.user_instructions,
        fetch_raw_webpage=request.fetch_raw_webpage,
        enable_web_search=sources.search_available,
        web_search_profile_enabled="web_search" in profile.enabled_builtin_tools,
        search_is_user_configured=sources.search_is_user_configured,
        enable_web_fetch=resolve_enable_web_fetch(profile.agent_security_raw),
        **surface.tool_flags,
        browser_source=profile.browser_source,
        dialog_policy=profile.dialog_policy,
        session_recording=profile.session_recording,
        kanban_default_board_id=profile.kanban_default_board_id,
        enable_memory=request.enable_memory,
        memory_require_confirmation=(
            True if (request.enable_memory and sandbox_capable) else request.memory_require_confirmation
        ),
        enable_memory_auto_extraction=(
            False
            if request.incognito_mode
            else (
                False
                if (
                    sandbox_capable
                    and (
                        profile.resolved is None
                        or profile.resolved.memory_policy is None
                        or not getattr(profile.resolved.memory_policy, "enable_auto_extraction", False)
                    )
                )
                else (request.enable_memory and request.enable_memory_auto_extraction)
            )
        ),
        enable_conversation_search=request.enable_conversation_search and not request.incognito_mode,
        incognito_mode=request.incognito_mode,
        enable_advanced_retrieval=(request.enable_advanced_retrieval if not surface.is_fast else False),
        embedding_config=sources.embedding_cfg if not surface.is_fast else None,
        reranker_config=sources.reranker_cfg if not surface.is_fast else None,
        auto_restore_domains=profile.auto_restore_domains if not surface.is_fast else [],
        agent_skill_ids=profile.agent_skill_ids,
        agent_skill_configs=profile.agent_skill_configs,
        subagent_ids=profile.agent_subagent_ids,
        security_config_raw=security_config_dict,
        security_overlay=security_overlay,
        agent_security_raw=profile.agent_security_raw,
        timezone=request.timezone,
        reasoning_display_mode=reasoning_display_mode,
        external_agents_config=external_agents_config if not surface.is_fast else None,
        force_external_agent=request.force_external_agent,
        image_generation=image_gen_params if not surface.is_fast else None,
        video_generation=video_gen_params if not surface.is_fast else None,
        tts=tts_params if not surface.is_fast else None,
        privacy_routing_raw=privacy_routing_obj,
        **privacy_params,
        code_execution_allow_network=code_exec_allow_network,
        event_log_dir=get_settings().database.event_log_dir,
        event_log_max_jsonl_line_bytes=get_settings().event_log_max_jsonl_line_bytes,
        locale=locale,
        max_iterations=profile.agent_max_iterations,
        memory_policy=profile.agent_memory_policy,
        memory_decay_profile=profile.agent_memory_decay_profile,
        memory_extraction_preset=profile.agent_memory_extraction_preset,
        engine_params=apply_moa_preset_activation(
            profile.engine_params,
            resolve_effective_moa_preset_id(
                engine_params=profile.engine_params,
                requested_preset_id=request.active_moa_preset_id,
                routing_tier=routing.tier,
                auto_moa_reasoning=request.auto_moa_reasoning,
                auto_moa_preset_id=request.auto_moa_preset_id,
            ),
        ),
        memory_shared_context_ids=context.memory_shared_context_ids,
        memory_shared_context_names=context.memory_shared_context_names,
        quote=request.quote,
        jit_subagents=enriched.jit_subagents if not surface.is_fast else None,
        session_loaded_skill_names=(
            context.session_loaded_skill_names if not surface.is_fast and not request.incognito_mode else None
        ),
        session_access_roots=context.session_access_roots_raw,
        declared_capabilities=tuple(declared_caps),
        declared_allowed_roots=(context.chat_workspace_dir,) if context.chat_workspace_dir else (),
        goal=request.goal.model_dump(exclude_none=True) if request.goal else None,
        openapi_services=profile.openapi_services,
        prompt_mode=surface.prompt_mode,
        search_depth=surface.search_depth,
        notify_targets=(profile.resolved.notify_targets if profile.resolved and not surface.is_fast else ()),
        tool_gateway_config=profile.tool_gateway_config,
        force_skill_manage=_is_learn_skill_authoring_query(final_query),
    )
    return (
        params,
        routing.tier,
        routing.specialty,
        routing.reason,
        enriched.mention_warnings,
        enriched.archive_restore_results,
    )


def _is_learn_skill_authoring_query(query: object) -> bool:
    """Detect /learn channel rewrites that require skill_manage_tool."""
    from app.core.channel_bridge.learn_handler import learn_authoring_prompt_text

    return learn_authoring_prompt_text(query) is not None
