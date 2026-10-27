"""Trigger unattended headless agent streams for goal continuation.

[INPUT] streaming, turn_lease (session claim + cancel token), gateway (busy / draining), failure, config_loader, ChatService, profile_resolver, tool_mount, GoalProvider, runtime_context, privacy_settings
[OUTPUT] GoalStreamAgentContext, trigger_goal_stream*
[POS] Headless goal continuation (dequeue / WAIT resume / loop restart) with chat-bound profile. The turn
runs under a server turn lease, taken before its agent is built, so a pause, the chat Stop button and the
emergency stop reach it.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.agent.goals.unattended.failure import TriggerFailurePolicy, handle_unattended_goal_stream_failure

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.agent.goals.types import Goal

logger = logging.getLogger(__name__)

_running_goal_tasks: set[asyncio.Task[None]] = set()


@dataclass(frozen=True, slots=True)
class GoalStreamAgentContext:
    """Profile fields needed for unattended goal continuation streams."""

    agent_id: str | None = None
    user_instructions: str | None = None
    subagent_ids: list[str] | None = None
    agent_skill_ids: list[str] | None = None
    enabled_builtin_tools: list[str] | None = None
    agent_security_raw: dict[str, object] | None = None


async def _resolve_goal_stream_agent_context(
    session_id: str,
) -> GoalStreamAgentContext:
    """Load chat-bound agent profile for unattended goal continuation."""
    from app.services.agent.params.profile_output_suffixes import (
        apply_profile_output_suffixes,
    )
    from app.services.agent.profile.profile_resolver import get_agent_profile_resolver
    from app.services.chat.chat_service import ChatService

    try:
        chat = await ChatService.get_chat_metadata(session_id)
    except Exception:
        logger.warning(
            "Failed to load chat metadata for goal stream session %s",
            session_id,
            exc_info=True,
        )
        return GoalStreamAgentContext()

    if chat is None or not chat.agent_id:
        return GoalStreamAgentContext()

    agent_id = chat.agent_id
    try:
        profile = await get_agent_profile_resolver().resolve(agent_id)
    except Exception:
        logger.warning(
            "Failed to resolve agent profile for goal stream session %s agent %s",
            session_id,
            agent_id,
            exc_info=True,
        )
        return GoalStreamAgentContext(agent_id=agent_id)

    if profile is None:
        return GoalStreamAgentContext(agent_id=agent_id)

    subagent_ids = list(profile.subagent_ids) if profile.subagent_ids else None
    user_instructions = profile.system_prompt

    if profile.agent_type == "team":
        from app.ai_agents.team_protocol import build_leader_protocol_prompt

        leader_protocol = await build_leader_protocol_prompt(
            subagent_ids or [],
            leader_id=agent_id,
            dynamic_discovery=True,
        )
        user_instructions = f"{user_instructions}\n\n{leader_protocol}" if user_instructions else leader_protocol

    user_instructions = apply_profile_output_suffixes(
        user_instructions,
        personality_style=profile.personality_style,
        engine_params=profile.engine_params,
        agent_id=agent_id,
    )
    return GoalStreamAgentContext(
        agent_id=agent_id,
        user_instructions=user_instructions,
        subagent_ids=subagent_ids,
        agent_skill_ids=list(profile.skill_ids) if profile.skill_ids else None,
        enabled_builtin_tools=list(profile.enabled_builtin_tools),
        agent_security_raw=profile.security_overrides,
    )


async def trigger_goal_stream(
    session_id: str,
    goal: Goal,
    *,
    provider: GoalProvider | None = None,
    on_failure: TriggerFailurePolicy = "needs_human_review",
    context: str = "goal stream",
) -> None:
    """Trigger a new agent stream for a dequeued goal.

    Loads full user config (model, search, security) and runs as unattended.
    """
    from app.ai_agents import GeneralAgentParams
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import (
        extract_fallback_model_configs,
        extract_retrieval_models,
        resolve_chat_fallback_chains_from_providers,
        resolve_vision_fallback_chain_for_agent,
        verify_search_service_available,
    )
    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
        resolve_model_config,
    )
    from app.core.security.privacy_settings import privacy_agent_params
    from app.services.agent.gateway import AgentBusyError, AgentDrainingError
    from app.services.agent.streaming import ai_agent_service_stream
    from app.services.agent.turn_lease import server_turn_lease

    logger.info(
        "trigger_goal_stream: starting stream for goal %s (%s)",
        goal.goal_id,
        goal.objective[:60],
    )

    # Arm unattended task safety airbag (zero-copy shadow snapshot baseline)
    try:
        from pathlib import Path

        from app.config.settings import settings
        from app.services.checkpoint.task_airbag_service import get_task_airbag_service

        ws_dir = str(Path(settings.project_dir).expanduser().resolve())
        await get_task_airbag_service().arm_airbag(goal.goal_id, ws_dir, session_id=session_id)
    except Exception as exc:
        logger.warning("Failed to automatically arm safety airbag for goal %s: %s", goal.goal_id, exc)

    user_cfgs = await load_user_configs()
    model_cfg = resolve_model_config(user_cfgs.providers_dict)
    model_cfg = enrich_model_capabilities(model_cfg, user_cfgs.providers_dict)
    model_cfg = enrich_model_context_window(model_cfg, user_cfgs.providers_dict)
    fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(user_cfgs.providers_dict)
    fallback_model_cfgs_list, fallback_lite_model_cfgs_list = resolve_chat_fallback_chains_from_providers(
        user_cfgs.providers_dict,
        require_tool_calling=True,
    )
    fallback_model_cfgs = fallback_model_cfgs_list or None
    fallback_lite_model_cfgs = fallback_lite_model_cfgs_list or None
    if fallback_model_cfgs and fallback_model_cfg is None:
        fallback_model_cfg = fallback_model_cfgs[0]
    if fallback_lite_model_cfgs and fallback_lite_model_cfg is None:
        fallback_lite_model_cfg = fallback_lite_model_cfgs[0]
    vision_fallback_model_cfg, vision_fallback_model_cfgs = resolve_vision_fallback_chain_for_agent(
        user_cfgs.providers_dict,
        main_model_cfg=model_cfg if model_cfg.supports_vision else None,
    )
    embedding_cfg, reranker_cfg = extract_retrieval_models(user_cfgs.retrieval_dict)

    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    GeneralAgentParams.model_rebuild(
        _types_namespace={
            "EmbeddingConfig": EmbeddingConfig,
            "RerankerConfig": RerankerConfig,
        }
    )

    security_config_raw = user_cfgs.security_config_dict or {}
    if not security_config_raw.get("yolo_mode_enabled", False):
        security_config_raw["yolo_mode_enabled"] = True
        security_config_raw["yolo_mode_enabled_at"] = time.time()
        security_config_raw["yolo_mode_timeout"] = None

    from app.core.agent.tool_description_locale import resolve_agent_params_locale
    from app.core.memory.proactive.settings import resolve_memory_enabled
    from app.services.agent.profile.profile_resolver import (
        DEFAULT_ENABLED_BUILTIN_TOOLS,
        resolve_builtin_tool_flags,
    )
    from app.services.agent.resolve_enable_web_fetch import resolve_enable_web_fetch
    from app.services.agent.tool_mount import ExecutionSurface, resolve_agent_mount

    memory_settings = user_cfgs.personal_settings_dict or {}

    agent_ctx = await _resolve_goal_stream_agent_context(session_id)

    enabled_builtin_tools: list[str] = list(agent_ctx.enabled_builtin_tools or DEFAULT_ENABLED_BUILTIN_TOOLS)
    tool_flags = resolve_agent_mount(
        ExecutionSurface.WEB_CHAT,
        resolve_builtin_tool_flags(enabled_builtin_tools),
    )

    params = GeneralAgentParams(
        query=goal.objective,
        chat_id=session_id,
        agent_id=agent_ctx.agent_id,
        user_instructions=agent_ctx.user_instructions,
        agent_skill_ids=agent_ctx.agent_skill_ids or [],
        subagent_ids=agent_ctx.subagent_ids,
        model_cfg=model_cfg,
        fallback_model_cfg=fallback_model_cfg,
        fallback_model_cfgs=fallback_model_cfgs,
        fallback_lite_model_cfg=fallback_lite_model_cfg,
        fallback_lite_model_cfgs=fallback_lite_model_cfgs,
        vision_fallback_model_cfg=vision_fallback_model_cfg,
        vision_fallback_model_cfgs=vision_fallback_model_cfgs or None,
        search_service_cfg=user_cfgs.search_cfg,
        embedding_config=embedding_cfg,
        reranker_config=reranker_cfg,
        security_config_raw=security_config_raw,
        agent_security_raw=agent_ctx.agent_security_raw,
        unattended_mode=True,
        enable_memory=resolve_memory_enabled(memory_settings),
        enable_web_search=user_cfgs.search_is_user_configured and await verify_search_service_available(user_cfgs.search_cfg),
        enable_web_fetch=resolve_enable_web_fetch(agent_ctx.agent_security_raw),
        web_search_profile_enabled="web_search" in enabled_builtin_tools,
        search_is_user_configured=user_cfgs.search_is_user_configured,
        **tool_flags,
        locale=resolve_agent_params_locale(
            personal_settings=memory_settings,
            channel="goal_stream",
        ),
        **privacy_agent_params(memory_settings),
    )

    from app.ai_agents.event_log_injector import (
        inject_event_log_config,
        sanitize_channel_event_log_session_id,
    )

    goal_event_log_sid = sanitize_channel_event_log_session_id(
        session_id,
        default_prefix="goal",
    )
    inject_event_log_config(params, session_id_override=goal_event_log_sid)

    async def _run_stream() -> None:
        turn_id = f"goal-turn-{uuid.uuid4().hex}"
        try:
            from app.services.agent.execution_cache.types import ExecutionMode
            from app.services.agent.runtime_context import build_agent_runtime_context

            extra_context = await build_agent_runtime_context(
                execution_mode=ExecutionMode.POOLED,
                base={"goal_provider": provider} if provider is not None else None,
            )
            # The lease is taken before the agent is built, as a chat turn takes its session, so a pause, the chat
            # Stop button and the emergency stop find this turn from the start. A turn that took the session first
            # (a message, or an earlier start of this goal) carries the goal on.
            async with server_turn_lease(session_id, turn_id) as cancel_token:
                async for _ in ai_agent_service_stream(params, cancel_token=cancel_token, extra_context=extra_context):
                    pass
        except (AgentBusyError, AgentDrainingError) as exc:
            logger.info("Goal %s: %s not started: %s", goal.goal_id, context, exc)
        except Exception as e:
            logger.error(
                "Background goal stream failed for goal %s: %s",
                goal.goal_id,
                e,
                exc_info=True,
            )
            await handle_unattended_goal_stream_failure(
                session_id,
                goal.goal_id,
                provider,
                on_failure=on_failure,
                context=context,
            )
        finally:
            _running_goal_tasks.discard(task)

    task = asyncio.create_task(_run_stream())
    _running_goal_tasks.add(task)


async def trigger_goal_stream_with_failure_policy(
    session_id: str,
    goal: Goal,
    provider: GoalProvider | None,
    *,
    on_failure: TriggerFailurePolicy = "needs_human_review",
    context: str = "goal stream",
) -> bool:
    """Trigger unattended stream; apply failure policy on setup or runtime errors."""
    try:
        await trigger_goal_stream(
            session_id,
            goal,
            provider=provider,
            on_failure=on_failure,
            context=context,
        )
        return True
    except Exception as exc:
        logger.error(
            "Failed to trigger %s for goal %s: %s",
            context,
            goal.goal_id,
            exc,
            exc_info=True,
        )
        await handle_unattended_goal_stream_failure(
            session_id,
            goal.goal_id,
            provider,
            on_failure=on_failure,
            context=context,
        )
        return False
