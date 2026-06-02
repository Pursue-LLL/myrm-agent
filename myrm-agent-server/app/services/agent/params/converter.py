"""[INPUT]
- app.ai_agents::GeneralAgentParams (POS: General Agent runtime parameter DTO)
- app.ai_agents.general_agent.llm_factory::select_tool_capable_model_cfg (POS: tool-capable main model selector)
- app.core.channel_bridge.config_loader::load_user_configs (POS: decrypted user config loader)
- app.core.channel_bridge.model_resolver::_fallback_model_from_providers / resolve_model_config (POS: default model resolution)

[OUTPUT]
- convert_to_general_agent_params(): build runtime params and routing metadata for GeneralAgent
- prevalidate_archive_restore_actions(): validate explicit archive restore actions before request persistence

[POS]
Agent request parameter conversion layer. Resolves user configuration, normalizes
model choices, and assembles `GeneralAgentParams` for execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from app.ai_agents import GeneralAgentParams
from app.ai_agents.general_agent.llm_factory import select_tool_capable_model_cfg
from app.core.channel_bridge.config_parsers import verify_search_service_available
from app.core.types import ChatHistoryReq, MCPServerConfig
from app.database.dto import PersonalityStyleLiteral

from .helpers import _extract_code_execution_network
from .media import _extract_media_generation_params
from .mention import (
    _build_mention_reference_context,
    _inject_mentioned_files_into_query,
)
from .models import AgentRequest
from .resolvers import _resolve_model_config

logger = logging.getLogger(__name__)
_MAX_ARCHIVE_RESTORE_ACTIONS = 3


class ArchiveRestoreRequestError(ValueError):
    """User-visible typed archive restore action validation failure."""


@dataclass(frozen=True, slots=True)
class BuiltArchiveRestoreActionContext:
    """Materialized archive restore context plus UI-safe result metadata."""

    prompt_context: str
    warnings: list[str]
    results: list[dict[str, object]]


async def _build_archive_restore_action_context(
    request: AgentRequest,
    chat_workspace_dir: str | None,
    *,
    record_allowed: bool = True,
) -> tuple[str, list[str]]:
    built = await _build_archive_restore_action_context_with_results(
        request,
        chat_workspace_dir,
        record_allowed=record_allowed,
    )
    return built.prompt_context, built.warnings


async def _build_archive_restore_action_context_with_results(
    request: AgentRequest,
    chat_workspace_dir: str | None,
    *,
    record_allowed: bool = True,
) -> BuiltArchiveRestoreActionContext:
    if not request.archive_restore_actions:
        return BuiltArchiveRestoreActionContext("", [], [])
    if not request.chat_id or not chat_workspace_dir:
        raise ArchiveRestoreRequestError("Archive restore action requires an initialized chat workspace.")
    if len(request.archive_restore_actions) > _MAX_ARCHIVE_RESTORE_ACTIONS:
        raise ArchiveRestoreRequestError(
            f"Archive restore action accepts at most {_MAX_ARCHIVE_RESTORE_ACTIONS} ranges per request."
        )

    from myrm_agent_harness.runtime.context.archive_restore_action import (
        ArchiveRestoreActionError,
        materialize_archive_restore_action,
    )

    parts: list[str] = []
    results: list[dict[str, object]] = []
    for action in request.archive_restore_actions:
        try:
            restored = await materialize_archive_restore_action(
                workspace_dir=chat_workspace_dir,
                chat_id=request.chat_id,
                restore_arg=action.restore_arg,
                record_allowed=record_allowed,
            )
        except ArchiveRestoreActionError as exc:
            raise ArchiveRestoreRequestError(str(exc)) from exc
        parts.append(restored.render_xml())
        results.append(restored.to_result().to_dict())

    if not parts:
        return BuiltArchiveRestoreActionContext("", [], [])
    return BuiltArchiveRestoreActionContext(
        "\n\n<archive_restore_actions>\n" + "\n".join(parts) + "\n</archive_restore_actions>",
        [],
        results,
    )


def _inject_archive_restore_actions_into_query(
    query: object,
    restore_context: str,
) -> object:
    if not restore_context:
        return query
    if isinstance(query, str):
        return f"{query}\n\n{restore_context}"
    if isinstance(query, list):
        next_query = list(query)
        next_query.append(
            {
                "type": "text",
                "text": f"Restored archived context for this turn:\n{restore_context}",
            }
        )
        return next_query
    return query


async def _resolve_default_chat_workspace_dir(
    chat_id: str,
    *,
    persist_workspace: bool,
) -> str | None:
    try:
        from pathlib import Path

        from myrm_agent_harness.toolkits.code_execution import (
            create_workspace_service,
        )

        from app.config.settings import get_settings
        from app.services.chat.chat_service import ChatService

        session_id = f"chat_{chat_id}"
        workspace_svc = create_workspace_service(
            root_dir=Path(get_settings().database.harness_dir),
        )
        workspace = await workspace_svc.get_or_create(session_id=session_id)
        chat_workspace_dir = workspace_svc.get_workspace_absolute_path(workspace)
        if persist_workspace:
            await ChatService.update_chat_fields(chat_id, {"workspace_dir": chat_workspace_dir})
        return chat_workspace_dir
    except Exception as exc:
        logger.warning(
            "Failed to resolve default sandbox workspace for chat %s: %s",
            chat_id,
            exc,
        )
        return None


async def prevalidate_archive_restore_actions(request: AgentRequest) -> None:
    """Validate explicit archive restore actions before the chat turn is persisted."""
    if not request.archive_restore_actions:
        return
    if not request.chat_id:
        raise ArchiveRestoreRequestError("Archive restore action requires an initialized chat workspace.")

    chat_workspace_dir: str | None = None
    chat_loaded = False
    db_had_workspace = False
    try:
        from app.services.chat.chat_service import ChatService

        chat = await ChatService.get_chat_metadata(request.chat_id)
        if chat:
            chat_loaded = True
            if chat.workspace_dir:
                chat_workspace_dir = chat.workspace_dir
                db_had_workspace = True
    except Exception as exc:
        logger.warning("Failed to load chat metadata for %s: %s", request.chat_id, exc)

    if not chat_workspace_dir:
        chat_workspace_dir = await _resolve_default_chat_workspace_dir(
            request.chat_id,
            persist_workspace=chat_loaded and not db_had_workspace,
        )

    await _build_archive_restore_action_context(
        request,
        chat_workspace_dir,
        record_allowed=False,
    )


async def convert_to_general_agent_params(
    request: AgentRequest,
    chat_history: list[list[str | dict[str, object]]],
) -> tuple[GeneralAgentParams, str | None, list[str], list[dict[str, object]]]:
    """将 Agent API 请求转换为 General Agent 参数。

    从 DB 读取用户配置（已解密），解析 API Key 和检索模型配置。
    chat_history 由调用方从 DB 加载后传入。

    Returns:
        Tuple of (GeneralAgentParams, routing_tier or None, context_reference_warnings, archive_restore_results)
    """

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import (
        extract_mcp_configs,
        extract_retrieval_models,
    )

    configs = await load_user_configs()

    providers_dict = configs.providers_dict if configs else None

    if request.model_selection:
        model_cfg = await _resolve_model_config(request.model_selection, providers_dict)
    else:
        from app.core.channel_bridge.model_resolver import resolve_model_config

        model_cfg = resolve_model_config(providers_dict)

    if configs and hasattr(configs, "model_cfg") and configs.model_cfg and configs.model_cfg.max_context_tokens is not None:
        model_cfg = model_cfg.model_copy(update={"max_context_tokens": configs.model_cfg.max_context_tokens})

    fallback_model_cfg = None
    if request.fallback_model_selection:
        try:
            fallback_model_cfg = await _resolve_model_config(request.fallback_model_selection, providers_dict)
        except ValueError:
            logger.warning("Failed to resolve fallback model, proceeding without it")

    safety_fallback_model_cfg = None
    if request.safety_fallback_model_selection:
        try:
            safety_fallback_model_cfg = await _resolve_model_config(request.safety_fallback_model_selection, providers_dict)
        except ValueError:
            logger.warning("Failed to resolve safety fallback model, proceeding without it")

    lite_model_cfg = None
    if request.lite_model_selection:
        try:
            lite_model_cfg = await _resolve_model_config(request.lite_model_selection, providers_dict)
        except ValueError:
            logger.warning("Failed to resolve filter model, proceeding without it")

    fallback_lite_model_cfg = None
    if request.fallback_lite_model_selection:
        try:
            fallback_lite_model_cfg = await _resolve_model_config(request.fallback_lite_model_selection, providers_dict)
        except ValueError:
            pass

    vision_fallback_model_cfg = None
    if request.vision_fallback_model_selection:
        try:
            vision_fallback_model_cfg = await _resolve_model_config(request.vision_fallback_model_selection, providers_dict)
        except ValueError:
            logger.warning("Failed to resolve vision fallback model, proceeding without it")

    model_cfg, selected_source = select_tool_capable_model_cfg(
        model_cfg,
        lite_model_cfg=lite_model_cfg,
        fallback_model_cfg=fallback_model_cfg,
        safety_fallback_model_cfg=safety_fallback_model_cfg,
        providers_dict=providers_dict,
    )
    if selected_source == "fallback":
        fallback_model_cfg = None
    elif selected_source == "lite":
        lite_model_cfg = None
    elif selected_source == "safety_fallback":
        safety_fallback_model_cfg = None

    routing_tier: str | None = None
    if request.light_model_selection or request.reasoning_model_selection:
        try:
            from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
                route_task,
            )

            light_model_cfg = None
            if request.light_model_selection:
                try:
                    light_model_cfg = await _resolve_model_config(request.light_model_selection, providers_dict)
                except ValueError:
                    logger.warning("Failed to resolve light model")

            light_fallback_cfg = None
            if request.fallback_light_model_selection:
                try:
                    light_fallback_cfg = await _resolve_model_config(request.fallback_light_model_selection, providers_dict)
                except ValueError:
                    pass

            reasoning_model_cfg = None
            if request.reasoning_model_selection:
                try:
                    reasoning_model_cfg = await _resolve_model_config(request.reasoning_model_selection, providers_dict)
                except ValueError:
                    logger.warning("Failed to resolve reasoning model")

            reasoning_fallback_cfg = None
            if request.fallback_reasoning_model_selection:
                try:
                    reasoning_fallback_cfg = await _resolve_model_config(
                        request.fallback_reasoning_model_selection, providers_dict
                    )
                except ValueError:
                    pass

            judge_llm = None
            if lite_model_cfg:
                from myrm_agent_harness.toolkits.llms import llm_manager

                try:
                    judge_llm = await llm_manager.get_llm_from_config(lite_model_cfg, "api_keys", None)
                except Exception as exc:
                    logger.debug("Failed to create judge LLM for smart routing: %s", exc)

            recent_routing_tiers = None
            if request.chat_id:
                try:
                    from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
                        RoutingTier,
                    )

                    from app.database.connection import get_session
                    from app.database.repositories.chat_repo import ChatRepository

                    async with get_session() as db:
                        tier_strings = await ChatRepository.get_recent_routing_tiers(db, request.chat_id)
                    if tier_strings:
                        recent_routing_tiers = [RoutingTier(t) for t in tier_strings]
                except Exception as exc:
                    logger.debug("Failed to fetch recent routing tiers: %s", exc)

            routing_result = await route_task(
                query=request.query,
                standard_model_cfg=model_cfg,
                light_model_cfg=light_model_cfg,
                reasoning_model_cfg=reasoning_model_cfg,
                standard_fallback_cfg=fallback_model_cfg,
                light_fallback_cfg=light_fallback_cfg,
                reasoning_fallback_cfg=reasoning_fallback_cfg,
                judge_llm=judge_llm,
                recent_tiers=recent_routing_tiers,
            )
            model_cfg = routing_result.model_cfg
            if routing_result.fallback_model_cfg is not None:
                fallback_model_cfg = routing_result.fallback_model_cfg
            routing_tier = routing_result.tier.value
            logger.warning(
                "Smart routing: tier=%s model=%s reason=%s",
                routing_result.tier.value,
                model_cfg.model,
                routing_result.reason,
            )
        except Exception:
            logger.warning("Smart routing failed, using default model", exc_info=True)

    search_cfg = configs.search_cfg if configs else None
    search_available = False
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

    user_instructions = request.user_instructions
    agent_skill_ids: list[str] = []
    agent_skill_configs: dict[str, dict] | None = None
    agent_subagent_ids: list[str] | None = None
    agent_security_raw: dict[str, object] | None = None
    agent_max_iterations: int | None = None
    agent_memory_policy = None
    agent_memory_decay_profile: str | None = None
    engine_params: dict[str, object] | None = None
    openapi_services: list[dict[str, object]] | None = None

    from app.services.agent.profile_resolver import (
        DEFAULT_ENABLED_BUILTIN_TOOLS,
        resolve_builtin_tool_flags,
    )

    enabled_builtin_tools: list[str] = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
    auto_restore_domains: list[str] = []
    resolved = None

    if request.agent_id:
        from app.services.agent.profile_resolver import get_agent_profile_resolver

        resolved = await get_agent_profile_resolver().resolve(request.agent_id)
        if resolved:
            if not request.agent_config and resolved.system_prompt:
                user_instructions = (
                    f"{user_instructions}\n\n{resolved.system_prompt}" if user_instructions else resolved.system_prompt
                )
            # Inject Hybrid Routing Rules if both browser and computer_use are enabled
            if resolved.enabled_builtin_tools and "browser" in resolved.enabled_builtin_tools and "computer_use" in resolved.enabled_builtin_tools:
                hybrid_routing_rule = (
                    "\n\n[HYBRID EXECUTION ROUTING RULES]\n"
                    "You have both 'browser' and 'computer_use' (desktop) tools available. You MUST follow these strict routing rules:\n"
                    "1. For ANY web page interaction (clicking links, filling forms, reading web content), you MUST use 'browser_snapshot' and 'browser_interact_tool'. It is 10x faster and more reliable.\n"
                    "2. DO NOT use 'desktop_snapshot' or 'desktop_interact_tool' to interact with web pages.\n"
                    "3. ONLY use 'desktop_snapshot' and 'desktop_interact_tool' when dealing with native OS dialogs (e.g., File Upload/Save dialogs, OS permission prompts) or browser extensions that 'browser_interact_tool' cannot see.\n"
                    "4. If 'browser_snapshot' or 'browser_interact_tool' warns you that an OS dialog is blocking the page, immediately switch to 'desktop_snapshot' and 'desktop_interact_tool'."
                )
                user_instructions = f"{user_instructions}{hybrid_routing_rule}" if user_instructions else hybrid_routing_rule.strip()

            agent_skill_ids = list(resolved.skill_ids)
            agent_skill_configs = resolved.skill_configs
            agent_subagent_ids = list(resolved.subagent_ids) if resolved.subagent_ids else None
            agent_security_raw = resolved.security_overrides
            enabled_builtin_tools = list(resolved.enabled_builtin_tools)
            agent_max_iterations = resolved.max_iterations
            agent_memory_policy = resolved.memory_policy
            agent_memory_decay_profile = resolved.memory_decay_profile
            engine_params = resolved.engine_params
            auto_restore_domains = list(resolved.auto_restore_domains)
            openapi_services = resolved.openapi_services or None

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
                        model_cfg = await _resolve_model_config(agent_model_selection, providers_dict)
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
                        model_cfg = _resolve_override_model(providers_dict, model_override=resolved.model)
                    except Exception:
                        logger.warning(
                            "Failed to resolve agent model '%s', keeping default",
                            resolved.model,
                        )

            if resolved.agent_type == "team" and agent_subagent_ids:
                from app.ai_agents.team_protocol import build_leader_protocol_prompt

                leader_protocol = await build_leader_protocol_prompt(agent_subagent_ids)
                user_instructions = (
                    f"{user_instructions}\n\n{leader_protocol}" if user_instructions else leader_protocol
                )

            from app.ai_agents.personality_templates import (
                DEFAULT_PERSONALITY_STYLE,
                get_personality_template,
            )

            if resolved.personality_style and resolved.personality_style != DEFAULT_PERSONALITY_STYLE:
                try:
                    template = get_personality_template(cast(PersonalityStyleLiteral, resolved.personality_style))
                    personality_suffix = f"\n\n**Communication Style**: {template.system_prompt_suffix}"
                    user_instructions = (
                        f"{user_instructions}{personality_suffix}" if user_instructions else personality_suffix.strip()
                    )
                except Exception:
                    logger.warning(
                        "Invalid personality style '%s' for agent '%s'",
                        resolved.personality_style,
                        request.agent_id,
                    )

    if mcp_configs and resolved:
        from app.services.agent.params.mcp_selection import apply_agent_mcp_selection

        mcp_configs = apply_agent_mcp_selection(
            mcp_configs,
            mcp_ids=resolved.mcp_ids or None,
            mcp_tool_selections=resolved.mcp_tool_selections or None,
        ) or None

    if request.engine_params:
        if engine_params:
            engine_params = {**engine_params, **request.engine_params}
        else:
            engine_params = dict(request.engine_params)

    if request.agent_config:
        cfg = request.agent_config
        agent_skill_ids = cfg.skill_ids
        if getattr(cfg, "skill_configs", None) is not None:
            agent_skill_configs = cfg.skill_configs
        enabled_builtin_tools = cfg.enabled_builtin_tools
        auto_restore_domains = list(cfg.auto_restore_domains)
        browser_engine = cfg.browser_engine if hasattr(cfg, "browser_engine") else (resolved.browser_engine if resolved else None)
        if getattr(cfg, "tool_gateway_config", None) is not None:
            tool_gateway_config = cfg.tool_gateway_config.model_dump(mode="json")
        else:
            tool_gateway_config = resolved.tool_gateway_config if resolved else None
    else:
        browser_engine = resolved.browser_engine if resolved else None
        tool_gateway_config = resolved.tool_gateway_config if resolved else None

    # Global PAT fallback logic
    if tool_gateway_config and isinstance(tool_gateway_config, dict):
        if tool_gateway_config.get("use_gateway") and not tool_gateway_config.get("auth_token"):
            ps_dict = configs.personal_settings_dict if configs else None
            if ps_dict and ps_dict.get("gateway_token"):
                tool_gateway_config["auth_token"] = ps_dict["gateway_token"]
                logger.info("Injected global gateway PAT into agent tool_gateway_config")

    if request.regenerate_instruction:
        regen_suffix = f"\n\n[Regeneration guidance: {request.regenerate_instruction}]"
        user_instructions = f"{user_instructions}{regen_suffix}" if user_instructions else regen_suffix.strip()

    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    GeneralAgentParams.model_rebuild(
        _types_namespace={
            "EmbeddingConfig": EmbeddingConfig,
            "RerankerConfig": RerankerConfig,
        }
    )

    security_config_dict = configs.security_config_dict if configs else None

    external_agents_config = None
    if configs and configs.external_agents_dict:
        agents_list = configs.external_agents_dict.get("agents")
        if isinstance(agents_list, list):
            external_agents_config = agents_list

    ps_dict = configs.personal_settings_dict if configs else None
    voice_dict = configs.voice_dict if configs else None
    image_gen_params, video_gen_params, tts_params = _extract_media_generation_params(ps_dict, providers_dict, enabled_builtin_tools, voice_dict)

    code_exec_allow_network = _extract_code_execution_network(ps_dict)

    locale = request.locale
    if not locale and ps_dict:
        locale = str(ps_dict.get("language", "en"))
    locale = locale or "en"

    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
    )

    selection_vision = request.model_selection.supports_vision if request.model_selection else None
    model_cfg = enrich_model_capabilities(model_cfg, providers_dict, selection_supports_vision=selection_vision)
    model_cfg = enrich_model_context_window(model_cfg, providers_dict)
    if fallback_model_cfg:
        fb_vision = request.fallback_model_selection.supports_vision if request.fallback_model_selection else None
        fallback_model_cfg = enrich_model_capabilities(fallback_model_cfg, providers_dict, selection_supports_vision=fb_vision)
        fallback_model_cfg = enrich_model_context_window(fallback_model_cfg, providers_dict)
    if safety_fallback_model_cfg:
        sf_vision = request.safety_fallback_model_selection.supports_vision if request.safety_fallback_model_selection else None
        safety_fallback_model_cfg = enrich_model_capabilities(
            safety_fallback_model_cfg,
            providers_dict,
            selection_supports_vision=sf_vision,
        )
        safety_fallback_model_cfg = enrich_model_context_window(safety_fallback_model_cfg, providers_dict)
    if lite_model_cfg:
        lite_vision = request.lite_model_selection.supports_vision if request.lite_model_selection else None
        lite_model_cfg = enrich_model_capabilities(lite_model_cfg, providers_dict, selection_supports_vision=lite_vision)
        lite_model_cfg = enrich_model_context_window(lite_model_cfg, providers_dict)
    if fallback_lite_model_cfg:
        fl_vision = request.fallback_lite_model_selection.supports_vision if request.fallback_lite_model_selection else None
        fallback_lite_model_cfg = enrich_model_capabilities(
            fallback_lite_model_cfg,
            providers_dict,
            selection_supports_vision=fl_vision,
        )
        fallback_lite_model_cfg = enrich_model_context_window(fallback_lite_model_cfg, providers_dict)
    if vision_fallback_model_cfg:
        vf_vision = request.vision_fallback_model_selection.supports_vision if request.vision_fallback_model_selection else None
        vision_fallback_model_cfg = enrich_model_capabilities(
            vision_fallback_model_cfg,
            providers_dict,
            selection_supports_vision=vf_vision,
        )
        vision_fallback_model_cfg = enrich_model_context_window(vision_fallback_model_cfg, providers_dict)

    jit_subagents = request.ephemeral_subagents
    task_adaptive_digest = None
    chat_workspace_dir: str | None = None
    chat_loaded = False
    db_had_workspace = False
    if request.chat_id:
        try:
            from app.services.chat.chat_service import ChatService

            chat = await ChatService.get_chat_metadata(request.chat_id)
            if chat:
                chat_loaded = True
                if jit_subagents is None and chat.ephemeral_subagents:
                    jit_subagents = chat.ephemeral_subagents
                if chat.task_adaptive_digest:
                    task_adaptive_digest = chat.task_adaptive_digest
                if chat.workspace_dir:
                    chat_workspace_dir = chat.workspace_dir
                    db_had_workspace = True
        except Exception as e:
            logger.warning(f"Failed to load chat metadata for {request.chat_id}: {e}")

    if not chat_workspace_dir and request.chat_id:
        chat_workspace_dir = await _resolve_default_chat_workspace_dir(
            request.chat_id,
            persist_workspace=chat_loaded and not db_had_workspace,
        )

    memory_shared_context_ids: list[str] = []
    try:
        from app.services.memory.shared_context import resolve_shared_context_ids

        memory_shared_context_ids = await resolve_shared_context_ids(
            agent_id=request.agent_id,
            channel_id="web_chat",
            conversation_id=request.chat_id,
            task_id=None,
        )
    except Exception as e:
        logger.warning("Failed to resolve shared memory contexts for agent request: %s", e)

    from app.config.settings import get_settings

    privacy_routing_obj: dict[str, object] | None = None
    if request.privacy_routing is not None:
        privacy_routing_obj = {str(k): v for k, v in request.privacy_routing.items()}

    final_query = request.query
    mention_warnings: list[str] = []
    archive_restore_results: list[dict[str, object]] = []
    restore_materialization = await _build_archive_restore_action_context_with_results(
        request,
        chat_workspace_dir,
    )
    restore_ctx = restore_materialization.prompt_context
    if restore_ctx:
        final_query = cast(
            object,
            _inject_archive_restore_actions_into_query(final_query, restore_ctx),
        )
    mention_warnings.extend(restore_materialization.warnings)
    archive_restore_results.extend(restore_materialization.results)

    if request.mention_references and chat_workspace_dir:
        max_ctx_tokens = model_cfg.max_context_tokens if model_cfg else None
        mention_ctx, mention_context_warnings, mention_tokens = await _build_mention_reference_context(
            request.mention_references, chat_workspace_dir, max_ctx_tokens
        )
        mention_warnings.extend(mention_context_warnings)
        if mention_ctx:
            final_query = _inject_mentioned_files_into_query(final_query, mention_ctx)
            logger.info(
                "Injected %d context references (%d tokens, %d warnings)",
                len(request.mention_references),
                mention_tokens,
                len(mention_warnings),
            )

    declared_caps = set()
    if security_config_dict and isinstance(security_config_dict.get("capabilities"), list):
        for c in security_config_dict["capabilities"]:
            if isinstance(c, str):
                declared_caps.add(c)
    if agent_security_raw and isinstance(agent_security_raw.get("capabilities"), list):
        for c in agent_security_raw["capabilities"]:
            if isinstance(c, str):
                declared_caps.add(c)

    is_fast_search = request.action_mode == "fast"
    search_depth: str = "normal"
    if is_fast_search:
        search_depth = request.search_depth if request.search_depth in ("normal", "deep") else "normal"
        fast_builtin: list[str] = ["answer_tool"]
        if search_depth == "deep":
            fast_builtin.append("browser")
        tool_flags = resolve_builtin_tool_flags(fast_builtin)
        prompt_mode = "search"
        search_available = True
        user_instructions = request.user_instructions
        agent_skill_ids = []
        agent_skill_configs = None
        mcp_configs = None
        agent_subagent_ids = None
        openapi_services = None
        agent_max_iterations = 50 if search_depth == "deep" else 30
        engine_params = {"max_tool_calls": 20 if search_depth == "deep" else 8}
        agent_memory_policy = {"write_policy": "conversation"}
    else:
        tool_flags = resolve_builtin_tool_flags(enabled_builtin_tools)
        prompt_mode = resolved.prompt_mode if resolved else "full"

    params = GeneralAgentParams(
        message_id=request.message_id,
        chat_id=request.chat_id,
        agent_id=request.agent_id,
        query=final_query,
        chat_history=cast(ChatHistoryReq, chat_history),
        model_cfg=model_cfg,
        fallback_model_cfg=fallback_model_cfg,
        safety_fallback_model_cfg=safety_fallback_model_cfg,
        lite_model_cfg=lite_model_cfg,
        fallback_lite_model_cfg=fallback_lite_model_cfg,
        vision_fallback_model_cfg=vision_fallback_model_cfg,
        search_service_cfg=search_cfg,
        mcp_cfg=mcp_configs,
        user_instructions=user_instructions,
        fetch_raw_webpage=request.fetch_raw_webpage,
        enable_web_search=search_available,
        **tool_flags,
        browser_engine=browser_engine,
        enable_memory=False if request.incognito_mode else request.enable_memory,
        memory_require_confirmation=request.memory_require_confirmation,
        enable_memory_auto_extraction=False if request.incognito_mode else (request.enable_memory and request.enable_memory_auto_extraction),
        incognito_mode=request.incognito_mode,
        enable_advanced_retrieval=request.enable_advanced_retrieval if not is_fast_search else False,
        embedding_config=embedding_cfg if not is_fast_search else None,
        reranker_config=reranker_cfg if not is_fast_search else None,
        auto_restore_domains=auto_restore_domains if not is_fast_search else [],
        agent_skill_ids=agent_skill_ids,
        agent_skill_configs=agent_skill_configs,
        subagent_ids=agent_subagent_ids,
        security_config_raw=security_config_dict,
        agent_security_raw=agent_security_raw,
        timezone=request.timezone,
        external_agents_config=external_agents_config if not is_fast_search else None,
        force_delegate_agent=request.force_delegate_agent,
        image_generation=image_gen_params if not is_fast_search else None,
        video_generation=video_gen_params if not is_fast_search else None,
        tts=tts_params if not is_fast_search else None,
        privacy_enabled=request.privacy_enabled,
        privacy_s2_action=request.privacy_s2_action,
        privacy_s3_action=request.privacy_s3_action,
        privacy_routing_raw=privacy_routing_obj,
        privacy_custom_keywords_s2=request.privacy_custom_keywords_s2 or [],
        privacy_custom_keywords_s3=request.privacy_custom_keywords_s3 or [],
        privacy_custom_patterns_s2=request.privacy_custom_patterns_s2 or [],
        privacy_custom_patterns_s3=request.privacy_custom_patterns_s3 or [],
        privacy_sensitive_tools_s2=request.privacy_sensitive_tools_s2 or [],
        privacy_sensitive_tools_s3=request.privacy_sensitive_tools_s3 or [],
        privacy_deep_scan=request.privacy_deep_scan,
        code_execution_allow_network=code_exec_allow_network,
        event_log_dir=get_settings().database.event_log_dir,
        event_log_max_jsonl_line_bytes=get_settings().event_log_max_jsonl_line_bytes,
        locale=locale,
        max_iterations=agent_max_iterations,
        memory_policy=agent_memory_policy,
        memory_decay_profile=agent_memory_decay_profile,
        engine_params=engine_params,
        memory_shared_context_ids=memory_shared_context_ids,
        quote=request.quote,
        jit_subagents=jit_subagents if not is_fast_search else None,
        task_adaptive_digest=task_adaptive_digest if not is_fast_search else None,
        declared_capabilities=tuple(declared_caps),
        declared_allowed_roots=(chat_workspace_dir,) if chat_workspace_dir else (),
        goal=request.goal.model_dump(exclude_none=True) if request.goal else None,
        openapi_services=openapi_services,
        prompt_mode=prompt_mode,
        search_depth=search_depth,
        notify_targets=resolved.notify_targets if resolved and not is_fast_search else (),
        tool_gateway_config=tool_gateway_config,
    )
    return params, routing_tier, mention_warnings, archive_restore_results
