"""Turn setup steps of the E1 agent turn: params, search gate, goal provider and runtime context.

[INPUT]
- app.services.agent.params::convert_to_general_agent_params (POS: AgentRequest → GeneralAgentParams conversion)
- app.services.agent.params.routing_memory::remember_turn_routing (POS: per-chat routing memory reused when a HITL turn resumes)
- app.services.agent.session_access_service::apply_directory_resume_grant (POS: directory grant carried by a resume)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: per-chat GoalProvider registry)
- app.services.agent.runtime_context::build_agent_runtime_context (POS: RunnableConfig context of one agent run)

[OUTPUT]
- TurnParams: converted agent params plus routing attribution of one turn
- build_turn_params: resume side effects (takeover decision, directory grant) then request → params conversion
- resolve_research_model: light-model config for Deep Research planning
- search_service_unavailable_detail: why a search-bound turn cannot run, or None
- prepare_goal_provider: goal provider of the chat with the request's goal budget applied
- build_turn_extra_context: runtime context handed to the agent run

[POS]
Setup half of the E1 turn body: every step between "history loaded" and "session built", each one awaitable on its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.types import ModelConfig
from app.services.agent.params import _resolve_model_config, convert_to_general_agent_params
from app.services.agent.params.routing_memory import remember_turn_routing

if TYPE_CHECKING:
    from fastapi import Request
    from myrm_agent_harness.agent.goals.protocols import GoalProvider

    from app.ai_agents import GeneralAgentParams
    from app.services.agent.params import AgentRequest

logger = logging.getLogger(__name__)

_SEARCH_AGENT_IDS: frozenset[str] = frozenset({"builtin-fast-search", "builtin-deep-search"})


@dataclass(frozen=True)
class TurnParams:
    params: GeneralAgentParams
    routing_tier: str | None
    routing_specialty: str | None
    routing_reason: str | None
    context_warnings: list[str]
    archive_restore_results: list[dict[str, object]]
    # Seed of the run context: a resume marks its HITL session active so the prompt cache is preserved.
    extra_context: dict[str, object] | None


async def build_turn_params(
    request: AgentRequest,
    chat_history: list[list[str | dict[str, object]]],
    http_request: Request,
) -> TurnParams:
    """Apply what a resume carries, then convert the request into agent params.

    Raises ``ArchiveRestoreRequestError`` when the request's archive restore actions are invalid.
    """
    if request.resume_value is not None:
        from langgraph.types import Command

        resume_action = request.resume_value.get("action")
        if request.chat_id and resume_action in ("completed", "skipped"):
            from app.services.approvals.registry import ApprovalRegistry

            decision = "approve" if resume_action == "completed" else "deny"
            await ApprovalRegistry.resolve_pending_browser_takeover_for_chat(
                request.chat_id,
                decision=decision,
            )

        logger.info(
            "Resume mode: chat_id=%s, decision=%s",
            request.chat_id,
            request.resume_value.get("decision"),
        )
        sandbox_active = False
        chat_workspace_dir: str | None = None
        if request.chat_id:
            try:
                from app.services.chat.chat_service import ChatService

                chat_meta = await ChatService.get_chat_metadata(request.chat_id)
                sandbox_active = bool(chat_meta and chat_meta.sandbox_base_dir)
                if chat_meta:
                    from app.services.chat.effective_workspace import (
                        resolve_effective_chat_workspace,
                    )

                    chat_workspace_dir = await resolve_effective_chat_workspace(
                        chat_meta,
                        jit_fallback=False,
                    )
            except Exception as exc:
                logger.warning("Failed to load sandbox state for resume grant: %s", exc)

        from app.services.agent.session_access_service import (
            apply_directory_resume_grant,
        )

        await apply_directory_resume_grant(
            request.chat_id,
            request.resume_value,
            sandbox_active=sandbox_active,
            workspace_dir=chat_workspace_dir,
        )
        (
            params,
            routing_tier,
            routing_specialty,
            routing_reason,
            context_warnings,
            archive_restore_results,
        ) = await convert_to_general_agent_params(
            request,
            chat_history,
            http_request=http_request,
        )
        params.query = Command(resume=request.resume_value)

        logger.info("HITL session marked active for cache preservation")
        return TurnParams(
            params=params,
            routing_tier=routing_tier,
            routing_specialty=routing_specialty,
            routing_reason=routing_reason,
            context_warnings=context_warnings,
            archive_restore_results=archive_restore_results,
            extra_context={"hitl_session_active": True},
        )

    (
        params,
        routing_tier,
        routing_specialty,
        routing_reason,
        context_warnings,
        archive_restore_results,
    ) = await convert_to_general_agent_params(
        request,
        chat_history,
        http_request=http_request,
    )
    remember_turn_routing(
        request,
        tier=routing_tier,
        specialty=routing_specialty,
        reason=routing_reason,
    )
    return TurnParams(
        params=params,
        routing_tier=routing_tier,
        routing_specialty=routing_specialty,
        routing_reason=routing_reason,
        context_warnings=context_warnings,
        archive_restore_results=archive_restore_results,
        extra_context=None,
    )


async def resolve_research_model(request: AgentRequest) -> ModelConfig | None:
    """Deep Research plans with the light model selection when the request carries one."""
    if request.action_mode != "deep_research" or not request.light_model_selection:
        return None
    try:
        from app.core.channel_bridge.config_loader import load_user_configs

        configs = await load_user_configs()
        providers_dict = configs.providers_dict if configs else None
        return await _resolve_model_config(request.light_model_selection, providers_dict)
    except Exception:
        logger.warning("Failed to resolve research model")
        return None


def search_service_unavailable_detail(request: AgentRequest, params: GeneralAgentParams) -> str | None:
    """User-facing reason the turn cannot run without a configured search service, or None when it can."""
    if request.action_mode == "deep_research" and not params.enable_web_search:
        return "Search service not configured. Deep Research requires a configured search service."
    if request.agent_id in _SEARCH_AGENT_IDS and not params.enable_web_search:
        return "Search service not configured. Please add a search service in Settings."
    if request.action_mode == "fast" and params.search_service_cfg is None:
        return "Search service not configured. Fast search requires a configured search service."
    return None


async def prepare_goal_provider(request: AgentRequest, text_content: str) -> GoalProvider | None:
    """Goal provider of the chat; a request that carries a goal creates it or re-budgets the active one."""
    if not request.chat_id:
        return None

    from app.services.agent.goals.goal_branch_stash import check_and_handle_branch_stash
    from app.services.agent.goals.goal_registry import GoalRegistry

    await check_and_handle_branch_stash(request.chat_id)
    goal_provider = GoalRegistry.get_or_create_provider(request.chat_id)
    if request.goal:
        from typing import cast

        from myrm_agent_harness.agent.goals.types import CheckpointMode, GoalBudget

        budget = GoalBudget(
            max_tokens=request.goal.max_tokens,
            max_usd=request.goal.max_usd,
            max_time_seconds=request.goal.max_time_seconds,
            max_turns=request.goal.max_turns,
            convergence_window=request.goal.convergence_window,
            loop_on_pause=request.goal.loop_on_pause,
            max_loop_restarts=request.goal.max_loop_restarts,
        )
        acceptance_criteria = request.goal.acceptance_criteria
        ui_summary = request.goal.ui_summary
        constraints = request.goal.constraints
        protected_paths = request.goal.protected_paths
        active_goal = await goal_provider.get_active_goal(request.chat_id)
        if not active_goal:
            checkpoint_mode_raw = getattr(request.goal, "checkpoint_mode", "none")
            checkpoint_mode = checkpoint_mode_raw if checkpoint_mode_raw in ("none", "per_todo") else "none"
            goal_objective = text_content.strip() or "User requested goal"
            resolved_ui_summary = ui_summary.strip() if ui_summary else goal_objective[:120]

            await goal_provider.create_goal(
                session_id=request.chat_id,
                objective=goal_objective,
                budget=budget,
                acceptance_criteria=acceptance_criteria,
                constraints=constraints,
                protected_paths=protected_paths,
                ui_summary=resolved_ui_summary,
                checkpoint_mode=cast(CheckpointMode, checkpoint_mode),
            )
        else:
            await goal_provider.set_budget(active_goal.goal_id, budget)
    return goal_provider


async def build_turn_extra_context(
    request: AgentRequest,
    params: GeneralAgentParams,
    *,
    base: dict[str, object] | None,
    goal_provider: GoalProvider | None,
) -> dict[str, object]:
    """Run context of the turn: goal provider, execution mode, user locale and, for a fresh turn, the prewarm join."""
    extra_context: dict[str, object] = {} if base is None else base
    extra_context["goal_provider"] = goal_provider

    from app.services.agent.runtime_context import (
        build_agent_runtime_context,
        resolve_stream_execution_mode,
    )

    extra_context = await build_agent_runtime_context(
        execution_mode=resolve_stream_execution_mode(),
        base=extra_context,
    )

    try:
        from app.core.channel_bridge.config_loader import load_user_configs

        configs = await load_user_configs()
        if configs and configs.personal_settings_dict:
            locale = configs.personal_settings_dict.get("locale")
            if locale:
                extra_context["locale"] = locale
            suggest_wf = configs.personal_settings_dict.get("suggestWorkflowMode")
            if suggest_wf is not None:
                extra_context["suggest_workflow_mode"] = bool(suggest_wf)
    except Exception as exc:
        logger.warning("Failed to load user locale for extra_context: %s", exc)

    if request.resume_value is None:
        if request.chat_id:
            from app.services.memory.ephemeral_delta_hydration import (
                ensure_chat_ephemeral_deltas_hydrated,
            )

            ensure_chat_ephemeral_deltas_hydrated(request.chat_id)

        from app.services.agent.execution_cache.prewarm.coordinator import (
            get_turn_prewarm_coordinator,
        )

        join_result = await get_turn_prewarm_coordinator().join_for_turn(
            params,
            action_mode=request.action_mode or "agent",
        )
        if join_result.preview is not None:
            extra_context["memory_brief_preview"] = join_result.preview
        if join_result.snapshot is not None:
            extra_context["memory_brief_snapshot"] = join_result.snapshot
        extra_context["memory_brief_status"] = join_result.brief_status
        extra_context["turn_prewarm_hit"] = join_result.prewarm_hit
        if join_result.prewarm_ms is not None:
            extra_context["turn_prewarm_ms"] = join_result.prewarm_ms
        extra_context["turn_prewarm_still_warming"] = join_result.still_warming

    return extra_context
