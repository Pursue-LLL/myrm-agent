"""Agent stream session teardown.

[INPUT]
- app.services.agent.streaming_support.hitl_timeout::arm_interrupt_timeout (POS: arms or reopens the timer of the interrupt the turn stopped at)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: persisted turn content)
- app.services.agent.stream_session.turn_history_sync::commit_turn_history_sync (POS: records that the agent thread mirrors the stored chat once a turn completed)
- app.services.agent.stream_session.turn_capability_terminal (POS: records the completed or failed terminal state of a turn that carries capability telemetry)
- myrm_agent_harness.utils.runtime.cancellation::CancellationRegistry (POS: Stop handle, unregistered when the turn ends)

[OUTPUT]
- finalize_agent_stream_session: persist the turn, record its terminal state, arm the HITL timeout of a pending interrupt and release the turn's session state

[POS]
Teardown half of the stream pipeline: runs once per turn after the chunk generator ends, however it ended.
"""

from __future__ import annotations

import logging
from contextvars import Token
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase
from myrm_agent_harness.core.security.types import EphemeralUserCredential, user_credentials_ctx
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationRegistry,
)

from app.services.agent.context_compaction_telemetry import (
    enqueue_context_compaction_telemetry,
)
from app.services.agent.memory_brief_telemetry import (
    enqueue_memory_brief_status_telemetry,
)
from app.services.agent.steering import SteeringRegistry
from app.services.agent.stream_session._memory_status_helpers import (
    build_memory_brief_status_payload,
    enrich_memory_brief_status_with_session_ephemeral_deltas,
    observe_memory_brief_status_payload,
)
from app.services.agent.stream_session.answered_cards import settle_answered_cards
from app.services.agent.stream_session.migration_readiness_anchor import (
    record_migration_first_turn_outcome,
)
from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    ClarificationTimeoutHolder,
)
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.stream_session.turn_capability_terminal import (
    has_turn_capability_terminal_context,
    record_turn_capability_completed_once,
    record_turn_capability_failed_once,
)
from app.services.agent.stream_session.turn_history_sync import commit_turn_history_sync
from app.services.agent.streaming_support.citation_persistence import (
    merge_memory_citation_fallback,
)
from app.services.agent.streaming_support.hitl_timeout import arm_interrupt_timeout
from app.services.agent.streaming_support.sse_helpers import (
    clear_context_task_metrics,
)

if TYPE_CHECKING:
    from app.services.agent.stream_session.lazy_session_gate import PendingSessionDraft

logger = logging.getLogger(__name__)


def _collector_has_unanswered_clarification(session: AgentStreamSession) -> bool:
    extra = session.collector.extra_data
    if not isinstance(extra, dict):
        return False
    clarification = extra.get("clarification")
    if not isinstance(clarification, dict):
        return False
    return clarification.get("answered") is False


def _clarification_timeout_needed(
    session: AgentStreamSession,
    clarification: ClarificationTimeoutHolder,
) -> bool:
    if clarification.pending:
        return True
    if session.request.chat_id is None:
        return False
    return _collector_has_unanswered_clarification(session)


async def _settle_session_draft(session: AgentStreamSession) -> PendingSessionDraft | None:
    """Commit the session the turn created lazily once it produced output, or discard the blank draft.

    Returns the draft so the caller can tell whether the stored chat exists.
    """
    draft = getattr(session, "pending_session_draft", None)
    if draft is not None and not draft.committed:
        if not session.collector.has_active_generation:
            logger.info(
                "Discarding uncommitted blank session draft: chat_id=%s",
                session.request.chat_id,
            )
        else:
            from app.services.agent.stream_session.lazy_session_gate import (
                commit_lazy_session_barrier,
            )

            await commit_lazy_session_barrier(session)
    return draft


def _assistant_turn_payload(session: AgentStreamSession, chat_id: str) -> tuple[str, dict[str, object]]:
    """The answer text and the extra data the turn is stored with; citation tags are lifted out of the text."""
    import re

    from myrm_agent_harness.api.hooks import (
        get_memory_runtime_budget,
        get_memory_runtime_injection,
    )

    content = session.collector.content
    extra_data = dict(session.collector.extra_data or {})
    if session.stream_ttft_ms is not None and session.stream_ttft_ms >= 0:
        extra_data["streamTtftMs"] = session.stream_ttft_ms
    merge_memory_citation_fallback(extra_data)
    preview = session.extra_context.get("memory_brief_preview") if isinstance(session.extra_context, dict) else None
    if isinstance(preview, dict):
        snapshot_id = preview.get("snapshot_id")
        if isinstance(snapshot_id, str) and snapshot_id.strip():
            extra_data["memoryBriefSnapshotId"] = snapshot_id.strip()
    brief_status = session.extra_context.get("memory_brief_status") if isinstance(session.extra_context, dict) else None
    # Parse and strip citations
    citations = list(dict.fromkeys(re.findall(r"<cite:([^>]+)>", content)))
    if citations:
        content = re.sub(r"<cite:[^>]+>", "", content)
        extra_data["citations"] = citations

    try:
        budget = get_memory_runtime_budget()
    except Exception as e:
        logger.warning("Failed to read memory budget in finalize: %s", e)
        budget = None
    if budget is not None:
        extra_data["memoryBudget"] = budget
    try:
        injection = get_memory_runtime_injection()
    except Exception as e:
        logger.warning("Failed to read memory injection in finalize: %s", e)
        injection = None
    status_payload = build_memory_brief_status_payload(brief_status, injection)
    status_payload = enrich_memory_brief_status_with_session_ephemeral_deltas(
        status_payload,
        chat_id,
    )
    if status_payload is not None:
        extra_data["memoryBriefStatus"] = status_payload
        observe_memory_brief_status_payload(phase="persist", payload=status_payload)
        enqueue_memory_brief_status_telemetry(
            phase="persist",
            payload=status_payload,
        )
    return content, extra_data


async def _persist_assistant_turn(session: AgentStreamSession, draft: PendingSessionDraft | None) -> None:
    """Store the assistant message of a turn that produced output in a chat that exists."""
    chat_id = session.request.chat_id
    if not (session.collector.has_persistable_turn and chat_id and (draft is None or draft.committed)):
        return

    from app.services.chat.chat_service import ChatService

    content, extra_data = _assistant_turn_payload(session, chat_id)
    await ChatService.persist_assistant_message_safe(
        chat_id,
        content,
        extra_data=extra_data,
        timezone=session.request.timezone,
        sibling_group_id=session.collector.sibling_group_id,
        request_message_id=session.request.message_id,
    )


async def _clear_turn_marker(session: AgentStreamSession) -> None:
    """Clear the crash auto-continue marker on normal completion (best-effort)."""
    if session.request.chat_id:
        try:
            await _clear_interrupted_turn_marker(session.request.chat_id)
        except Exception as marker_exc:
            logger.debug("Turn marker cleanup skipped: %s", marker_exc)


def _arm_pending_interrupt_timeout(
    session: AgentStreamSession,
    approval: ApprovalTimeoutHolder,
    clarification_pending: bool,
) -> None:
    """Arm the timer of the interrupt the turn stopped at, or reopen one that has none."""
    if session.request.chat_id:
        arm_interrupt_timeout(
            session.request.chat_id,
            session.params,
            approval_timeout=approval.value,
            clarification_pending=clarification_pending,
            awaiting_answer=session.collector.has_pending_hitl_replay(),
        )


def _schedule_compaction_drain(session: AgentStreamSession) -> None:
    """Drain in the background when the turn left compaction debt behind."""
    if session.request.chat_id:
        from myrm_agent_harness.agent.context_management.tracking.task_metrics import (
            get_task_metrics,
        )

        metrics = get_task_metrics(session.request.chat_id)
        if metrics and getattr(metrics, "compaction_debt_pending", False):
            from app.services.chat.chat_service import ChatService

            logger.info(
                "Scheduling background drain for %s due to compaction debt.",
                session.request.chat_id,
            )
            ChatService.schedule_background_drain(session.request.chat_id)


def _release_turn_state(session: AgentStreamSession) -> None:
    """Flush the compaction telemetry and drop what the turn registered: Stop handle, steering and goal."""
    enqueue_context_compaction_telemetry(session.request.chat_id)
    clear_context_task_metrics(session.request.chat_id)
    target_msg_id = getattr(session.params, "message_id", None) or getattr(session.request, "message_id", None)
    if target_msg_id:
        CancellationRegistry.unregister(target_msg_id)
    if session.request.chat_id:
        SteeringRegistry.unregister(session.request.chat_id)
        from app.services.agent.goals.goal_registry import GoalRegistry

        GoalRegistry.unregister(session.request.chat_id)


async def _flush_skill_evolution_residual(session: AgentStreamSession) -> None:
    """Queue the trace slice left over at the end of the session for skill evolution (best-effort)."""
    cancel_token = getattr(session, "cancel_token", None)
    is_cancelled = cancel_token.is_cancelled if cancel_token is not None else False
    params = getattr(session, "params", None)
    enable_skill_manage = getattr(params, "enable_skill_manage", False) if params is not None else False

    if session.collector.has_content and session.request.chat_id and not is_cancelled and enable_skill_manage:
        # Flush remaining sliding window slice (sub-threshold residual)
        try:
            from myrm_agent_harness.agent.skills.evolution.core.types import (
                EvolutionRequest,
                EvolutionType,
            )
            from myrm_agent_harness.agent.skills.evolution.infra.integration import (
                get_global_evolution_integration,
            )
            from myrm_agent_harness.agent.skills.evolution.infra.queue import (
                QueuePriority,
            )

            evo_integration = get_global_evolution_integration()
            if evo_integration and session.request.chat_id:
                remaining = evo_integration._slice_cursors.pop(session.request.chat_id, None)
                if remaining:
                    _count, ids = remaining
                    if ids and evo_integration.queue:
                        await evo_integration.queue.enqueue(
                            EvolutionRequest(
                                evolution_type=EvolutionType.SLICE_EXTRACTION,
                                skill_id=f"slice_{session.request.chat_id}_{len(ids)}_calls",
                                reason="Session-end residual trace slice",
                                session_id=session.request.chat_id,
                                tool_call_ids=ids,
                                agent_id=getattr(session.request, "agent_id", None),
                            ),
                            priority=QueuePriority.LOW,
                        )
        except Exception as flush_exc:
            logger.debug("Slice window flush skipped: %s", flush_exc)


async def _record_turn_capability_terminal(session: AgentStreamSession) -> None:
    """Record how a turn that waits on no answer ended, for the turn capability telemetry."""
    if has_turn_capability_terminal_context(session.request):
        if session.cancel_token.is_cancelled:
            await record_turn_capability_failed_once(session, "abort")
        elif session.had_fatal_error or not (session.collector.has_content or session.collector.tool_stuck_paused):
            await record_turn_capability_failed_once(session, "unknown_error")
        else:
            await record_turn_capability_completed_once(session)


def _close_run_digest(session: AgentStreamSession) -> None:
    """End the run digest of the chat and announce the session outcome to the lifecycle webhooks."""
    if session.request.chat_id:
        from app.services.copilot.run_digest_store import RunDigestStore

        phase = RunDigestPhase.COMPLETED
        if session.cancel_token.is_cancelled:
            phase = RunDigestPhase.CANCELLED
        elif session.had_fatal_error:
            phase = RunDigestPhase.ERROR
        RunDigestStore.end_run(
            session.request.chat_id,
            phase=phase,
            progress_steps=list(session.collector._progress_steps),
        )
        _publish_session_lifecycle_webhook_event(
            chat_id=session.request.chat_id,
            phase=phase,
            agent_id=getattr(session.request, "agent_id", None),
            was_cancelled=session.cancel_token.is_cancelled,
            had_fatal_error=session.had_fatal_error,
        )


async def finalize_agent_stream_session(
    session: AgentStreamSession,
    token_ctx: Token[tuple[EphemeralUserCredential, ...]],
    approval: ApprovalTimeoutHolder,
    clarification: ClarificationTimeoutHolder,
) -> None:
    """Run the teardown of one turn: persist it, record its end, arm the pending interrupt's timer, release its state."""
    user_credentials_ctx.reset(token_ctx)
    draft = await _settle_session_draft(session)

    await settle_answered_cards(session)

    await _persist_assistant_turn(session, draft)
    await _clear_turn_marker(session)

    await record_migration_first_turn_outcome(
        request=session.request,
        had_fatal_error=session.had_fatal_error,
        has_assistant_content=session.collector.has_content,
        live_readiness_status=session.migration_live_readiness_status,
    )

    clarification_sched_needed = _clarification_timeout_needed(session, clarification)

    _arm_pending_interrupt_timeout(session, approval, clarification_sched_needed)
    _schedule_compaction_drain(session)
    _release_turn_state(session)
    await _flush_skill_evolution_residual(session)

    pending_hitl = bool(
        clarification_sched_needed
        or (approval.value and not clarification_sched_needed)
        or session.collector.has_pending_hitl_replay()
    )
    await commit_turn_history_sync(session, pending_hitl=pending_hitl)
    if not pending_hitl:
        await _record_turn_capability_terminal(session)

    if pending_hitl:
        logger.info(
            "Deferring collector cleanup for pending HITL: chat_id=%s",
            session.request.chat_id,
        )
    else:
        _close_run_digest(session)
        session.collector.cleanup()


def _publish_session_lifecycle_webhook_event(
    *,
    chat_id: str,
    phase: RunDigestPhase,
    agent_id: str | None,
    was_cancelled: bool,
    had_fatal_error: bool,
) -> None:
    """Publish session_completed / session_failed for outbound lifecycle webhooks."""
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    if phase == RunDigestPhase.COMPLETED:
        event_type = AppEventType.SESSION_COMPLETED
    else:
        event_type = AppEventType.SESSION_FAILED

    get_event_bus().publish(
        AppEvent(
            event_type=event_type,
            data={
                "chat_id": chat_id,
                "agent_id": agent_id,
                "phase": phase.value,
                "was_cancelled": was_cancelled,
                "had_fatal_error": had_fatal_error,
            },
        )
    )


async def _clear_interrupted_turn_marker(chat_id: str) -> None:
    """Remove the write-ahead marker after a turn completes normally."""
    from sqlalchemy import delete

    from app.database.models.chat import InterruptedTurnMarker
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        await db.execute(delete(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == chat_id))
        await db.commit()
