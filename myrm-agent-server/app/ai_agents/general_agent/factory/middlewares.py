"""[INPUT]
- app.ai_agents.general_agent.factory.runtime::SandboxRuntime (POS: 装配第三阶段；只创建执行资源，不组装中间件或提示词。)

[OUTPUT]
- build_agent_middlewares: build_agent_middlewares

[POS]
装配第四阶段；把记忆回调、护栏、上下文管线与 MoA 组装成有序中间件列表。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from langchain.agents.middleware.types import AgentMiddleware
    from langchain_core.language_models import BaseChatModel

    from app.ai_agents.general_agent.agent import GeneralAgent

from app.ai_agents.general_agent.factory.runtime import SandboxRuntime

logger = logging.getLogger(__name__)


async def build_agent_middlewares(
    agent_wrapper: "GeneralAgent",
    effective_chat_id: str,
    runtime: SandboxRuntime,
    *,
    lite_llm: "BaseChatModel",
) -> "list[AgentMiddleware]":
    from myrm_agent_harness.agent.context_management.infra.cache_policy import (
        resolve_cache_ttl_prune_policy,
    )
    from myrm_agent_harness.agent.middlewares import create_context_pipeline_middleware
    from myrm_agent_harness.agent.workspace_rules import workspace_rules_middleware

    from app.ai_agents.agent_middlewares import (
        ephemeral_delta_middleware,
        memory_context_middleware,
        proactive_pack_middleware,
        project_roadmap_middleware,
        user_instructions_middleware,
        widget_capability_middleware,
    )
    from app.core.utils.media_file_reader import read_uploaded_media_file_content

    from ..agent_middlewares.citation_rules_middleware import citation_rules_middleware
    from ..agent_middlewares.tool_selection_middleware import tool_selection_middleware
    from ..callbacks import (
        make_notes_load,
        make_notes_persist,
        make_summary_persist_with_wiki_archive,
    )
    from .support import _get_budget_pressure_fn

    compress_offload_cb = runtime.compress_offload_cb
    context_snapshot_cb = runtime.context_snapshot_cb
    compress_eviction_cb = runtime.compress_eviction_cb
    pre_compact_cb = runtime.pre_compact_cb
    archive_checkpoint_store = runtime.archive_checkpoint_store
    archive_checkpoint_notifier = runtime.archive_checkpoint_notifier
    from myrm_agent_harness.agent.middlewares import (
        PlanConfirmMiddleware,
        RateLimitMiddleware,
    )
    from myrm_agent_harness.agent.middlewares.guardrails import (
        GuardrailMiddleware,
        GuardrailProvider,
        SkillBoundaryProvider,
    )

    from app.services.skills.permission_service import create_async_permission_checker

    permission_checker = await create_async_permission_checker()

    guardrail_providers: list[GuardrailProvider] = [
        SkillBoundaryProvider(permission_checker=permission_checker),
    ]

    try:
        from app.services.security.tenant_guardrail import TenantPolicyProvider

        guardrail_providers.append(TenantPolicyProvider())
    except ImportError:
        pass

    guardrail_middleware = GuardrailMiddleware(
        providers=guardrail_providers,
        agent_id=agent_wrapper.agent_id,
        session_id=effective_chat_id,
    )

    logger.info("Skill permission checker enabled for user: sandbox")

    time_decay_half_life_days = 90.0
    if agent_wrapper.memory_decay_profile == "permanent":
        time_decay_half_life_days = 3650.0
    elif agent_wrapper.memory_decay_profile == "fast":
        time_decay_half_life_days = 7.0

    context_pipeline_middleware = create_context_pipeline_middleware(
        llm=lite_llm,
        summarizer_llm=lite_llm,
        tail_budget_ratio=agent_wrapper.tail_budget_ratio,
        on_summary_persist=make_summary_persist_with_wiki_archive(
            enable_wiki=agent_wrapper.enable_wiki,
            wiki_archive_llm=(lite_llm if agent_wrapper.enable_wiki else None),
        ),
        on_compress_offload=compress_offload_cb,
        on_compress_eviction=compress_eviction_cb,
        on_context_snapshot=context_snapshot_cb,
        on_pre_compact=pre_compact_cb,
        archive_checkpoint_store=archive_checkpoint_store,
        on_archive_checkpoint=archive_checkpoint_notifier,
        session_notes_llm=lite_llm,
        on_notes_persist=make_notes_persist(effective_chat_id),
        on_notes_load=make_notes_load(effective_chat_id),
        budget_pressure_fn=_get_budget_pressure_fn(),
        time_decay_half_life_days=time_decay_half_life_days,
        cache_ttl_prune_config=resolve_cache_ttl_prune_policy(agent_wrapper.model_cfg.model).config,
        file_content_reader=read_uploaded_media_file_content,
    )

    middlewares_list = [
        RateLimitMiddleware(warning_threshold_pct=0.8, debounce_seconds=300.0),
        PlanConfirmMiddleware(),
        user_instructions_middleware,
        workspace_rules_middleware,
        project_roadmap_middleware,
        memory_context_middleware,
        widget_capability_middleware,
        citation_rules_middleware,
        tool_selection_middleware,
        context_pipeline_middleware,
    ]

    from app.services.agent.stream_session.moa_overlay_setup import (
        build_moa_overlay_middleware,
    )

    moa_middleware = await build_moa_overlay_middleware(
        agent_wrapper.engine_params,
        unattended=bool(getattr(agent_wrapper, "unattended_mode", False)),
    )
    if moa_middleware is not None:
        middlewares_list.append(moa_middleware)
        agent_wrapper.moa_overlay_skip_reason = None
        logger.info("MoA advisor overlay middleware mounted (chat_id=%s)", effective_chat_id)
    else:
        from app.services.agent.stream_session.moa_overlay_setup import (
            resolve_moa_overlay_skip_reason,
        )

        agent_wrapper.moa_overlay_skip_reason = await resolve_moa_overlay_skip_reason(
            agent_wrapper.engine_params,
        )

    if guardrail_middleware:
        middlewares_list.insert(0, guardrail_middleware)

    # Human-tail blocks run after context pipeline so compression cannot strip them; the knowledge pack goes
    # first so explicit session deltas stay closest to the end of the user turn.
    middlewares_list.extend(
        [
            proactive_pack_middleware,
            ephemeral_delta_middleware,
        ]
    )

    middlewares = cast("list[AgentMiddleware]", middlewares_list)

    return middlewares
