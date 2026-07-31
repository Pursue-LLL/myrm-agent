"""Agent stream session orchestrator — business flow for General Agent SSE.

[INPUT]
- app.services.agent.params (POS: request conversion)
- app.services.agent.stream_session.stream_generator (POS: SSE generation)

[OUTPUT]
- run_agent_stream: full orchestration returning StreamingResponse | JSONResponse

[POS]
Service-layer stream orchestration. **Session mutex (`ChatSessionReservation`) before user persist**; busy → SSE AgentBusyError via stream_busy. HTTP route decorators remain in api/agents/general_agent/streaming.py.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams

from fastapi.responses import JSONResponse, StreamingResponse
from myrm_agent_harness.agent.middlewares.approval.scheduler import (
    ApprovalTimeoutScheduler,
)
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationMonitor,
    CancellationRegistry,
    CancellationToken,
)
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.core.types import ModelConfig
from app.services.agent.params import (
    AgentRequest,
    ArchiveRestoreRequestError,
    _resolve_model_config,
    convert_to_general_agent_params,
    prevalidate_archive_restore_actions,
)
from app.services.agent.runtime_context import prefer_direct_agent_stream
from app.services.agent.steering_registry import SteeringRegistry
from app.services.agent.stream_session.chat_history_bootstrap import (
    persist_user_message_and_load_history,
    stream_text_content,
)
from app.services.agent.stream_session.consensus_stream_setup import (
    resolve_consensus_stream_models,
)
from app.services.agent.stream_session.migration_bound_project import (
    apply_migration_bound_project,
)
from app.services.agent.stream_session.reconnect import try_stream_reconnect
from app.services.agent.stream_session.risk_gate import check_stream_risk
from app.services.agent.stream_session.session_reservation import ChatSessionReservation
from app.services.agent.stream_session.stream_busy import agent_busy_streaming_response
from app.services.agent.stream_session.stream_generator import (
    AgentStreamSession,
    build_disconnect_checker,
    launch_buffered_stream,
)
from app.services.agent.stream_session.stream_lane_factory import (
    archive_restore_error_response,
)
from app.services.agent.stream_session.turn_capability_terminal import (
    TurnCapabilityFailureReason,
    has_turn_capability_terminal_context,
    record_turn_capability_send_failed,
)
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

logger = logging.getLogger(__name__)

_ACTION_MODE_FEATURE_GATE: dict[str, str] = {
    "deep_research": "deep_research",
    "consensus": "consensus",
}

_SEARCH_AGENT_IDS: frozenset[str] = frozenset(
    {"builtin-fast-search", "builtin-deep-search"}
)

# Gateway hygiene limit: ~120K tokens (rough character-to-token ratio) to prevent OOM
_GATEWAY_MAX_INPUT_CHARS: int = 360_000


async def run_agent_stream(
    request: AgentRequest,
    http_request: Request,
) -> StreamingResponse | JSONResponse:
    """Streaming Agent execution with gateway lifecycle management.

    Backend is the authoritative store: persists user message first,
    then loads chat history from DB (frontend no longer sends chat_history).
    """
    stream_started_at_monotonic = time.perf_counter()
    request = prefer_direct_agent_stream(request)

    async def _record_terminal_failure_if_needed(
        reason: TurnCapabilityFailureReason,
    ) -> None:
        if not has_turn_capability_terminal_context(request):
            return
        await record_turn_capability_send_failed(request, reason)

    async for _ in http_request.stream():
        pass

    from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry

    registry = GlobalStreamRegistry.get()
    reconnect_response = await try_stream_reconnect(request, http_request)
    if reconnect_response is not None:
        return reconnect_response

    gated_feature = _ACTION_MODE_FEATURE_GATE.get(request.action_mode or "")
    if gated_feature:
        from myrm_agent_harness.core.features import get_features

        if not get_features().enabled(gated_feature):
            await _record_terminal_failure_if_needed("server_error")
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"{request.action_mode} is disabled via Feature Gate"
                },
            )

    text_content = stream_text_content(request)

    # Gateway hygiene check: block massive malicious payloads before they hit the agent harness
    if len(text_content) > _GATEWAY_MAX_INPUT_CHARS:
        logger.warning(
            f"Gateway rejected massive payload: length={len(text_content)} chars"
        )
        await _record_terminal_failure_if_needed("server_error")
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Request exceeds gateway token limits (approx 120K tokens). Please reduce the size of your input."
            },
        )

    if request.resume_value is None:
        risk_block = await check_stream_risk(text_content, request.chat_id)
        if risk_block is not None:
            await _record_terminal_failure_if_needed("server_error")
            return risk_block
        try:
            await prevalidate_archive_restore_actions(request)
        except ArchiveRestoreRequestError as exc:
            await _record_terminal_failure_if_needed("archive_restore_invalid")
            return archive_restore_error_response(exc)

    session_reservation = ChatSessionReservation()
    try:
        busy_error = session_reservation.try_reserve(
            request.chat_id,
            message_id=request.message_id,
        )
        if busy_error is not None:
            return agent_busy_streaming_response(request.message_id)

        chat_history = await persist_user_message_and_load_history(
            request,
            text_content=text_content,
        )

        await apply_migration_bound_project(request)

        extra_context: dict[str, object] | None = None
        try:
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

                if request.chat_id:
                    if not ApprovalTimeoutScheduler.get().resolve_if_first(
                        request.chat_id
                    ):
                        logger.warning(
                            "Resume rejected (timeout already resolved): chat_id=%s",
                            request.chat_id,
                        )
                        await _record_terminal_failure_if_needed("unknown_error")
                        return JSONResponse(
                            status_code=409,
                            content={
                                "detail": "This HITL request has already been resolved by timeout."
                            },
                        )

                logger.info(
                    "Resume mode: chat_id=%s, decision=%s",
                    request.chat_id,
                    request.resume_value.get("decision"),
                )
                params, routing_tier, context_warnings, archive_restore_results = (
                    await convert_to_general_agent_params(
                        request,
                        chat_history,
                        http_request=http_request,
                    )
                )
                params.query = Command(resume=request.resume_value)

                extra_context = {"hitl_session_active": True}
                logger.info("HITL session marked active for cache preservation")
            else:
                params, routing_tier, context_warnings, archive_restore_results = (
                    await convert_to_general_agent_params(
                        request,
                        chat_history,
                        http_request=http_request,
                    )
                )
        except ArchiveRestoreRequestError as exc:
            await _record_terminal_failure_if_needed("archive_restore_invalid")
            return archive_restore_error_response(exc)

        research_model_cfg: ModelConfig | None = None
        if request.action_mode == "deep_research" and request.light_model_selection:
            try:
                from app.core.channel_bridge.config_loader import load_user_configs

                configs = await load_user_configs()
                providers_dict = configs.providers_dict if configs else None
                if request.light_model_selection is not None:
                    research_model_cfg = await _resolve_model_config(
                        request.light_model_selection, providers_dict
                    )
            except Exception:
                logger.warning("Failed to resolve research model")

        if request.action_mode == "deep_research" and not params.enable_web_search:
            await _record_terminal_failure_if_needed("server_error")
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Search service not configured. Deep Research requires a configured search service."
                },
            )

        if request.agent_id in _SEARCH_AGENT_IDS and not params.enable_web_search:
            await _record_terminal_failure_if_needed("server_error")
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Search service not configured. Please add a search service in Settings."
                },
            )

        if request.action_mode == "fast" and params.search_service_cfg is None:
            await _record_terminal_failure_if_needed("server_error")
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Search service not configured. Fast search requires a configured search service."
                },
            )

        cancel_token = CancellationToken(request_id=request.message_id)
        CancellationRegistry.register(cancel_token)

        steering_token = SteeringToken() if request.chat_id else None
        if steering_token and request.chat_id:
            SteeringRegistry.register(request.chat_id, steering_token)

        from app.services.agent.goal_registry import (
            GoalRegistry,
            check_and_handle_branch_stash,
        )

        goal_provider = None
        if request.chat_id:
            await check_and_handle_branch_stash(request.chat_id)
            goal_provider = GoalRegistry.get_or_create_provider(request.chat_id)
            if request.goal:
                from myrm_agent_harness.agent.goals.types import GoalBudget

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
                    checkpoint_mode_raw = getattr(
                        request.goal, "checkpoint_mode", "none"
                    )
                    checkpoint_mode = (
                        checkpoint_mode_raw
                        if checkpoint_mode_raw in ("none", "per_todo")
                        else "none"
                    )
                    from typing import cast

                    from myrm_agent_harness.agent.goals.types import CheckpointMode

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

        if extra_context is None:
            extra_context = {}
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
        except Exception as e:
            logger.warning(f"Failed to load user locale for extra_context: {e}")

        if request.resume_value is None:
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

        is_long_running_task = request.action_mode in (
            "deep_research",
            "agentic_search",
            "consensus",
        )
        collector = StreamContentCollector(
            sibling_group_id=request.sibling_group_id, chat_id=request.chat_id
        )

        consensus_config, consensus_ref_cfgs, consensus_agg_cfg = (
            await resolve_consensus_stream_models(
                request,
            )
        )

        session = AgentStreamSession(
            request=request,
            http_request=http_request,
            params=params,
            cancel_token=cancel_token,
            steering_token=steering_token,
            routing_tier=routing_tier,
            context_warnings=context_warnings,
            archive_restore_results=archive_restore_results,
            research_model_cfg=research_model_cfg,
            registry=registry,
            collector=collector,
            monitor=CancellationMonitor(
                token=cancel_token,
                disconnect_checker=lambda: False,
                check_interval=0.5,
            ),
            is_long_running_task=is_long_running_task,
            goal_provider=goal_provider,
            extra_context=extra_context or {},
            stream_started_at_monotonic=stream_started_at_monotonic,
            consensus_config=consensus_config,
            consensus_ref_model_cfgs=consensus_ref_cfgs,
            consensus_agg_model_cfg=consensus_agg_cfg,
            entitlement_preflight_text=(
                text_content if request.resume_value is None else None
            ),
        )
        session.monitor = CancellationMonitor(
            token=cancel_token,
            disconnect_checker=build_disconnect_checker(session),
            check_interval=0.5,
        )

        # Write-ahead marker for crash auto-continue (best-effort, non-blocking)
        if (
            request.chat_id
            and request.resume_value is None
            and not is_long_running_task
        ):
            try:
                await _write_interrupted_turn_marker(request, params)
            except Exception as marker_exc:
                logger.debug("Turn marker write skipped: %s", marker_exc)

        session_reservation.transfer_to_stream()
        return await launch_buffered_stream(session)
    finally:
        session_reservation.release()


async def _write_interrupted_turn_marker(
    request: AgentRequest,
    params: GeneralAgentParams,
) -> None:
    """Persist a write-ahead marker so a crash leaves a recoverable trace."""
    import uuid

    from sqlalchemy import delete

    from app.database.models.chat import InterruptedTurnMarker
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        await db.execute(
            delete(InterruptedTurnMarker).where(
                InterruptedTurnMarker.chat_id == request.chat_id
            )
        )
        marker = InterruptedTurnMarker(
            id=str(uuid.uuid4()),
            chat_id=request.chat_id,
            user_message_id=request.message_id or "",
            action_mode=request.action_mode or "fast",
            agent_id=getattr(request, "agent_id", None),
            serialized_params=params.model_dump(mode="json", exclude={"chat_history"}),
        )
        db.add(marker)
        await db.commit()
