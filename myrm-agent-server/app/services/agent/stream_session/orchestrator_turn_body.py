"""Post-reserve agent turn execution for early buffered SSE (E1).

[INPUT]
- app.services.agent.stream_session.orchestrator helpers (POS: shared turn setup)
- app.services.agent.stream_session.pre_reply_compact_sse (POS: idle compact SSE)
- app.services.agent.stream_session.stream_pump::pump_to_buffer (POS: SSE pump)

[OUTPUT]
- launch_early_buffered_stream: return StreamingResponse immediately after reserve
- execute_agent_turn_after_reserve: compact → persist → agent session → pump (background)

[POS]
E1 early-stream path: clients subscribe while pre-reply compact and orchestrator setup run.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Request
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
from sqlalchemy import delete

from app.core.types import ModelConfig
from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.params import (
    ArchiveRestoreRequestError,
    _resolve_model_config,
    convert_to_general_agent_params,
)
from app.services.agent.steering_registry import SteeringRegistry
from app.services.agent.stream_session import chat_history_bootstrap
from app.services.agent.stream_session.migration_bound_project import (
    apply_migration_bound_project,
)
from app.services.agent.stream_session.session_reservation import ChatSessionReservation
from app.services.agent.stream_session.stream_generator import (
    AgentStreamSession,
    build_disconnect_checker,
)
from app.services.agent.stream_session.stream_pump import pump_to_buffer
from app.services.agent.stream_session.turn_capability_terminal import (
    TurnCapabilityFailureReason,
)
from app.services.agent.streaming_support.sse_helpers import error_sse
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.chat.compact_service import CompactResult

if TYPE_CHECKING:
    from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry

    from app.ai_agents import GeneralAgentParams
    from app.services.agent.params import AgentRequest

logger = logging.getLogger(__name__)

_SEARCH_AGENT_IDS: frozenset[str] = frozenset(
    {"builtin-fast-search", "builtin-deep-search"}
)


async def _fail_buffered_turn(
    buffer: object,
    message_id: str | None,
    detail: str,
) -> None:
    await buffer.append(error_sse(detail, message_id))  # type: ignore[attr-defined]
    await buffer.end_stream()  # type: ignore[attr-defined]


async def launch_early_buffered_stream(
    *,
    request: AgentRequest,
    http_request: Request,
    text_content: str,
    stream_started_at_monotonic: float,
    registry: GlobalStreamRegistry,
    buffer: object,
    session_reservation: ChatSessionReservation,
    record_terminal_failure: Callable[[TurnCapabilityFailureReason], Awaitable[None]],
) -> StreamingResponse | JSONResponse:
    """Start turn execution in background and return stream or multiplexed accepted JSON."""

    async def _background_turn() -> None:
        try:
            await execute_agent_turn_after_reserve(
                request=request,
                http_request=http_request,
                text_content=text_content,
                stream_started_at_monotonic=stream_started_at_monotonic,
                registry=registry,
                buffer=buffer,
                record_terminal_failure=record_terminal_failure,
            )
        except Exception as exc:
            logger.error(
                "Background agent turn failed for message_id=%s: %s",
                request.message_id,
                exc,
                exc_info=True,
            )
            await _fail_buffered_turn(
                buffer,
                request.message_id,
                "Stream setup failed",
            )

    task = asyncio.create_task(
        _background_turn(),
        name=f"agent_turn_{request.message_id or 'unknown'}",
    )
    task.add_done_callback(
        lambda t: (
            t.exception() if not t.cancelled() and t.exception() is not None else None
        )
    )
    session_reservation.transfer_to_stream()
    if getattr(request, "multiplexed", False):
        return JSONResponse(
            content={"status": "accepted", "message_id": request.message_id},
        )
    return StreamingResponse(
        content=buffer.subscribe(),  # type: ignore[attr-defined]
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


async def execute_agent_turn_after_reserve(
    *,
    request: AgentRequest,
    http_request: Request,
    text_content: str,
    stream_started_at_monotonic: float,
    registry: GlobalStreamRegistry,
    buffer: object,
    record_terminal_failure: Callable[[TurnCapabilityFailureReason], Awaitable[None]],
) -> None:
    """Run compact → persist → session build → pump after HTTP stream is already open."""
    # Commit the user row before any optional profile/model-window/compact work.
    # The multiplexed HTTP response is already accepted at this point; API
    # observers must see the turn even when stale-context setup is slow.
    #
    # Resolve helpers from the module at call time.  Uvicorn's dev reloader can
    # reload this module before reloading its dependency; the fallback keeps an
    # in-flight old worker from crashing with a mixed-generation ImportError.
    persisted_message_id: str | None = None
    chat_history: list[list[str | dict[str, object]]] | None = None
    persist_user_message = getattr(
        chat_history_bootstrap,
        "persist_user_message",
        None,
    )
    load_chat_history = getattr(chat_history_bootstrap, "load_chat_history", None)
    if callable(persist_user_message) and callable(load_chat_history):
        persisted_message_id = await persist_user_message(
            request,
            text_content=text_content,
        )
    else:
        # Mixed-generation hot reload fallback.  A fresh process always takes
        # the split path above; an old worker remains functional until it exits.
        chat_history = await chat_history_bootstrap.persist_user_message_and_load_history(
            request,
            text_content=text_content,
        )

    pre_reply_compact_result: CompactResult | None = None
    pre_reply_compact_sse_sent = False
    if request.resume_value is None and request.chat_id and request.message_id:
        from app.services.agent.stream_session.pre_reply_compact_sse import (
            run_pre_reply_compact_with_sse,
        )

        pre_reply_compact_result = await run_pre_reply_compact_with_sse(
            buffer,
            chat_id=request.chat_id,
            message_id=request.message_id,
            agent_id=request.agent_id,
            request_engine_params=request.engine_params,
        )
        pre_reply_compact_sse_sent = bool(
            pre_reply_compact_result
            and (
                (
                    pre_reply_compact_result.compacted
                    and pre_reply_compact_result.tokens_saved > 0
                )
                or pre_reply_compact_result.attempted
            )
        )

    if chat_history is None:
        chat_history = await load_chat_history(
            request,
            exclude_message_id=persisted_message_id,
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
                if not ApprovalTimeoutScheduler.get().resolve_if_first(request.chat_id):
                    logger.warning(
                        "Resume rejected (timeout already resolved): chat_id=%s",
                        request.chat_id,
                    )
                    await record_terminal_failure("unknown_error")
                    await _fail_buffered_turn(
                        buffer,
                        request.message_id,
                        "This HITL request has already been resolved by timeout.",
                    )
                    return

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
                    logger.warning(
                        "Failed to load sandbox state for resume grant: %s", exc
                    )

            from app.services.agent.session_access_service import (
                apply_directory_resume_grant,
            )

            await apply_directory_resume_grant(
                request.chat_id,
                request.resume_value,
                sandbox_active=sandbox_active,
                workspace_dir=chat_workspace_dir,
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
        await record_terminal_failure("archive_restore_invalid")
        await _fail_buffered_turn(buffer, request.message_id, str(exc))
        return

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
        await record_terminal_failure("server_error")
        await _fail_buffered_turn(
            buffer,
            request.message_id,
            "Search service not configured. Deep Research requires a configured search service.",
        )
        return

    if request.agent_id in _SEARCH_AGENT_IDS and not params.enable_web_search:
        await record_terminal_failure("server_error")
        await _fail_buffered_turn(
            buffer,
            request.message_id,
            "Search service not configured. Please add a search service in Settings.",
        )
        return

    if request.action_mode == "fast" and params.search_service_cfg is None:
        await record_terminal_failure("server_error")
        await _fail_buffered_turn(
            buffer,
            request.message_id,
            "Search service not configured. Fast search requires a configured search service.",
        )
        return

    cancel_token = CancellationToken(request_id=request.message_id)
    CancellationRegistry.register(cancel_token)

    steering_token = SteeringToken() if request.chat_id else None
    if steering_token and request.chat_id:
        SteeringRegistry.register(request.chat_id, steering_token)

    from app.services.agent.goals.goal_registry import (
        GoalRegistry,
        check_and_handle_branch_stash,
    )

    goal_provider = None
    if request.chat_id:
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
                checkpoint_mode = (
                    checkpoint_mode_raw
                    if checkpoint_mode_raw in ("none", "per_todo")
                    else "none"
                )
                goal_objective = text_content.strip() or "User requested goal"
                resolved_ui_summary = (
                    ui_summary.strip() if ui_summary else goal_objective[:120]
                )

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
    except Exception as exc:
        logger.warning("Failed to load user locale for extra_context: %s", exc)

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

    is_long_running_task = request.action_mode in ("deep_research", "agentic_search")
    collector = StreamContentCollector(
        sibling_group_id=request.sibling_group_id, chat_id=request.chat_id
    )
    if request.chat_id:
        from app.services.copilot.run_digest_store import RunDigestStore

        RunDigestStore.begin_run(request.chat_id)

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
        entitlement_preflight_text=(
            text_content if request.resume_value is None else None
        ),
        pre_reply_compact_result=pre_reply_compact_result,
        pre_reply_compact_sse_sent=pre_reply_compact_sse_sent,
    )
    session.monitor = CancellationMonitor(
        token=cancel_token,
        disconnect_checker=build_disconnect_checker(session),
        check_interval=0.5,
    )

    if request.chat_id and request.resume_value is None and not is_long_running_task:
        try:
            await write_interrupted_turn_marker(request, params)
        except Exception as marker_exc:
            logger.debug("Turn marker write skipped: %s", marker_exc)

    await pump_to_buffer(session, buffer)


async def write_interrupted_turn_marker(
    request: AgentRequest,
    params: GeneralAgentParams,
) -> None:
    """Persist a write-ahead marker so a crash leaves a recoverable trace."""
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
