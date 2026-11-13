"""Kanban agent run — builds the worker agent for one task and drains its event stream.

[INPUT]
- app.ai_agents.agents::AgentFactory, GeneralAgentParams (POS: Agent construction.)
- app.core.channel_bridge.config_loader::load_user_configs (POS: User provider, retrieval and security configuration.)
- app.services.agent.tool_mount::ExecutionSurface, resolve_agent_mount (POS: Tool mount of the kanban surface.)
- app.services.agent.profile.profile_resolver::DEFAULT_ENABLED_BUILTIN_TOOLS, resolve_builtin_tool_flags (POS: Builtin tool defaults and flags.)
- task_runner.stream::_StreamAccumulator (POS: Stream-event accumulation; owned by the caller, who reads what the stream ended on.)

[OUTPUT]
- KANBAN_CHANNEL: Channel name every kanban run is attributed to.
- execute_agent: Runs one task through a freshly built GeneralAgent and returns ``(success, text)``.

[POS]
Agent assembly and stream draining for a single kanban task: resolves the user's model and
security configuration, mounts the kanban worker tools, streams the agent and folds its events
into a result. Kept apart from ``KanbanTaskRunner`` so the runner owns scheduling and outcome
decisions while this module owns the agent build.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.services.agent.profile.profile_resolver import (
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    resolve_builtin_tool_flags,
)
from app.services.agent.tool_mount import ExecutionSurface, resolve_agent_mount

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.api import KanbanStore
    from myrm_agent_harness.toolkits.kanban.types import KanbanTask

    from app.services.kanban.task_runner.profile import _ResolvedProfile
    from app.services.kanban.task_runner.stream import _StreamAccumulator

logger = logging.getLogger(__name__)

KANBAN_CHANNEL = "kanban"


async def execute_agent(
    store: KanbanStore,
    task: KanbanTask,
    context: str | list[dict[str, object]],
    profile: _ResolvedProfile | None,
    *,
    acc: _StreamAccumulator,
    workspace_root: str | None = None,
    goal_provider: GoalProvider | None = None,
) -> tuple[bool, str]:
    """Build the worker agent for ``task``, stream it into ``acc`` and return ``(success, text)``.

    ``acc`` belongs to the caller, who reads from it what the stream ended on (see ``stopped_for_approval``).
    """
    from app.ai_agents.agents import AgentFactory, GeneralAgentParams
    from app.config.settings import get_settings
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import (
        extract_fallback_model_configs,
        extract_retrieval_models,
        resolve_vision_fallback_chain_for_agent,
        verify_search_service_available,
    )
    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
        resolve_model_config,
    )

    user_cfgs = await load_user_configs()

    board = await store.get_board(task.board_id) if task.board_id else None
    zombie_timeout = board.settings.zombie_timeout_seconds if board and board.settings else 120

    embedding_cfg, reranker_cfg = extract_retrieval_models(user_cfgs.retrieval_dict)
    fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(
        user_cfgs.providers_dict,
    )
    from app.core.channel_bridge.config_parsers import resolve_chat_fallback_chains_from_providers

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

    from myrm_agent_harness.toolkits.retriever.embedding.factory import (
        EmbeddingConfig,
    )
    from myrm_agent_harness.toolkits.retriever.reranker.factory import (
        RerankerConfig,
    )

    GeneralAgentParams.model_rebuild(
        _types_namespace={
            "EmbeddingConfig": EmbeddingConfig,
            "RerankerConfig": RerankerConfig,
        },
    )

    security_config_raw = dict(user_cfgs.security_config_dict or {})
    if not security_config_raw.get("yolo_mode_enabled", False):
        security_config_raw["yolo_mode_enabled"] = True
        security_config_raw["yolo_mode_enabled_at"] = time.time()
        security_config_raw["yolo_mode_timeout"] = None

    model_override = task.model_override or (profile.model if profile else None)
    model_cfg = resolve_model_config(
        user_cfgs.providers_dict,
        model_override=model_override,
    )
    model_cfg = enrich_model_capabilities(model_cfg, user_cfgs.providers_dict)
    model_cfg = enrich_model_context_window(model_cfg, user_cfgs.providers_dict)

    vision_fallback_model_cfg, vision_fallback_model_cfgs = resolve_vision_fallback_chain_for_agent(
        user_cfgs.providers_dict,
        main_model_cfg=model_cfg if model_cfg.supports_vision else None,
    )

    memory_shared_context_ids: list[str] = []
    try:
        from app.services.memory.shared_context.shared_context import (
            resolve_shared_context_ids,
        )

        memory_shared_context_ids = await resolve_shared_context_ids(
            agent_id=task.agent_id,
            channel_id=KANBAN_CHANNEL,
            conversation_id=task.task_id,
            task_id=task.task_id,
        )
    except Exception as exc:
        logger.warning(
            "Task %s: failed to resolve shared memory contexts: %s",
            task.task_id[:8],
            exc,
        )

    enabled_builtin_tools: list[str] = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
    if profile is not None:
        enabled_builtin_tools = list(profile.enabled_builtin_tools)

    if "kanban" not in enabled_builtin_tools:
        enabled_builtin_tools.append("kanban")

    task_user_instructions: str | None = profile.system_prompt if profile else None
    agent_subagent_ids = list(profile.subagent_ids) if profile and profile.subagent_ids else None
    if profile and profile.agent_type == "team":
        from app.ai_agents.team_protocol import build_leader_protocol_prompt

        leader_protocol = await build_leader_protocol_prompt(
            agent_subagent_ids or [],
            leader_id=task.agent_id,
            dynamic_discovery=True,
        )
        task_user_instructions = f"{task_user_instructions}\n\n{leader_protocol}" if task_user_instructions else leader_protocol

    if profile:
        from app.services.agent.params.response_locale_suffix import (
            apply_response_locale_suffix,
        )

        task_user_instructions = apply_response_locale_suffix(
            task_user_instructions,
            engine_params=profile.engine_params,
        )

    declared_roots: tuple[str, ...] = ()
    if workspace_root:
        declared_roots = (workspace_root,)

    from app.core.agent.tool_description_locale import resolve_agent_params_locale
    from app.core.memory.proactive.settings import (
        resolve_conversation_search_enabled,
        resolve_memory_enabled,
    )
    from app.core.security.privacy_settings import privacy_agent_params
    from app.services.agent.resolve_enable_web_fetch import resolve_enable_web_fetch

    kanban_agent_security_raw = profile.security_overrides if profile else None
    memory_settings = user_cfgs.personal_settings_dict or {}

    params = GeneralAgentParams(
        query=context,
        model_cfg=model_cfg,
        fallback_model_cfg=fallback_model_cfg,
        fallback_model_cfgs=fallback_model_cfgs,
        fallback_lite_model_cfg=fallback_lite_model_cfg,
        fallback_lite_model_cfgs=fallback_lite_model_cfgs,
        vision_fallback_model_cfg=vision_fallback_model_cfg,
        vision_fallback_model_cfgs=vision_fallback_model_cfgs or None,
        search_service_cfg=user_cfgs.search_cfg,
        chat_id=task.task_id,
        agent_id=task.agent_id,
        embedding_config=embedding_cfg,
        reranker_config=reranker_cfg,
        security_config_raw=security_config_raw,
        agent_security_raw=kanban_agent_security_raw,
        channel_name=KANBAN_CHANNEL,
        declared_allowed_roots=declared_roots,
        enable_web_search=(user_cfgs.search_is_user_configured and await verify_search_service_available(user_cfgs.search_cfg)),
        enable_web_fetch=resolve_enable_web_fetch(kanban_agent_security_raw),
        kanban_tool_mode="worker",
        kanban_current_task_id=task.task_id,
        kanban_max_runtime_seconds=task.max_runtime_seconds,
        kanban_zombie_timeout_seconds=zombie_timeout,
        **resolve_agent_mount(
            ExecutionSurface.KANBAN,
            resolve_builtin_tool_flags(enabled_builtin_tools),
        ),
        auto_restore_domains=list(profile.auto_restore_domains) if profile else [],
        unattended_mode=True,
        enable_memory=resolve_memory_enabled(memory_settings),
        user_instructions=task_user_instructions,
        agent_skill_ids=list(dict.fromkeys((*(profile.skill_ids if profile else []), *task.extra_skill_ids))),
        subagent_ids=(list(profile.subagent_ids) if profile and profile.subagent_ids else None),
        max_iterations=profile.max_iterations if profile else None,
        memory_policy=profile.memory_policy if profile else None,
        memory_decay_profile=profile.memory_decay_profile if profile else None,
        memory_extraction_preset=(profile.memory_extraction_preset if profile else None),
        engine_params=profile.engine_params if profile else None,
        memory_shared_context_ids=memory_shared_context_ids,
        enable_conversation_search=resolve_conversation_search_enabled(
            memory_settings,
        ),
        locale=resolve_agent_params_locale(
            personal_settings=memory_settings,
            channel=KANBAN_CHANNEL,
        ),
        event_log_dir=get_settings().database.event_log_dir,
        event_log_max_jsonl_line_bytes=get_settings().event_log_max_jsonl_line_bytes,
        **privacy_agent_params(memory_settings),
    )

    from app.services.agent.execution_cache import (
        ExecutionMode,
        finalize_agent_session,
    )
    from app.services.agent.runtime_context import build_agent_runtime_context

    runtime_context = await build_agent_runtime_context(
        execution_mode=ExecutionMode.EPHEMERAL,
    )
    if goal_provider is not None:
        runtime_context["goal_provider"] = goal_provider

    agent = AgentFactory.create_general_agent(params)
    agent.approval_session_key = f"kanban:{task.task_id}"

    from app.services.agent.session_credential_assembler import (
        session_credentials_scope,
    )

    async with session_credentials_scope(
        oauth_credentials_dict=user_cfgs.oauth_credentials_dict,
        providers_dict=user_cfgs.providers_dict,
    ):
        try:

            async def _open_stream(query_input: object) -> AsyncGenerator[dict[str, object], None]:
                async for event in agent.process_stream(
                    query=query_input,
                    chat_history=None,
                    chat_id=task.task_id,
                    context=runtime_context,
                ):
                    if isinstance(event, dict):
                        yield event

            from app.services.agent.fission_config import (
                max_parallel_from_engine_params,
            )
            from app.services.agent.swarm_fission_resume import (
                stream_with_swarm_fission_resume,
            )

            async for event in stream_with_swarm_fission_resume(
                agent,
                context,
                _open_stream,
                max_concurrent=max_parallel_from_engine_params(profile.engine_params if profile else None),
            ):
                acc.add(event)

            if task.metadata is not None:
                if acc.usage:
                    task.metadata["last_token_usage"] = acc.usage
                if acc.cost_usd is not None:
                    task.metadata["last_cost_usd"] = acc.cost_usd
            else:
                meta = {}
                if acc.usage:
                    meta["last_token_usage"] = acc.usage
                if acc.cost_usd is not None:
                    meta["last_cost_usd"] = acc.cost_usd
                task.metadata = meta

            return acc.to_result()
        finally:
            await finalize_agent_session(
                agent,
                chat_id=task.task_id,
                agent_id=params.agent_id,
                extra_context=runtime_context,
            )
