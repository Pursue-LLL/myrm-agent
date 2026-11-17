"""Agent stream session teardown.

[INPUT]
- app.services.agent.streaming_support.hitl_timeout::arm_interrupt_timeout (POS: arms or reopens the timer of the interrupt the turn stopped at)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: persisted turn content)
- app.services.agent.stream_session.turn_history_sync::commit_turn_history_sync (POS: records that the agent thread mirrors the stored chat once a turn completed)
- app.services.agent.stream_session.turn_end (POS: compaction drain, run digest close and lifecycle event, shared with the end of a timer-resumed turn)
- app.services.agent.stream_session.turn_capability_terminal (POS: records the completed or failed terminal state of a turn that carries capability telemetry)
- myrm_agent_harness.utils.runtime.cancellation::CancellationRegistry (POS: Stop handle, unregistered when the turn ends)
- app.services.agent.steering::SteeringRegistry (POS: registry of the steering tokens of running turns; the turn gives back the token it registered)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: registry of the goal providers of running turns; the turn gives back the provider it registered)
- myrm_agent_harness.agent.streaming.interrupt_events::INTERRUPT_ID_KEY (POS: key under which a stored card remembers the pause it was announced for)

[OUTPUT]
- finalize_agent_stream_session: persist the turn, record its terminal state, arm the HITL timeout of a pending interrupt, remove the replay marker the turn wrote and release the turn's session state
- release_unfinished_turn: tear down a turn whose stream never reached finalize (safety net of the turn body); a stopped turn takes the replay marker it wrote with it
- release_turn_registrations: give back the Stop handle, steering token and goal provider a turn registered, each by the handle the turn holds
- assistant_turn_payload: the content and extra data a collector's turn is stored with (shared with the persistence of a timer-resumed turn)

[POS]
Teardown half of the stream pipeline: finalize runs once per turn after the chunk generator ends, however it ended; the
exits that skip the generator (a Stop while the turn is queued behind its project, a failure in setup or in the pump)
are torn down by release_unfinished_turn, called from the turn body's finally.
"""

from __future__ import annotations

import logging
from contextvars import Token
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.streaming.interrupt_events import INTERRUPT_ID_KEY
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
from app.services.agent.stream_session.turn_end import close_run_digest, schedule_compaction_drain
from app.services.agent.stream_session.turn_history_sync import commit_turn_history_sync
from app.services.agent.streaming_support.citation_persistence import (
    merge_memory_citation_fallback,
)
from app.services.agent.streaming_support.hitl_timeout import arm_interrupt_timeout
from app.services.agent.streaming_support.sse_helpers import (
    clear_context_task_metrics,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.utils.runtime.steering import SteeringToken

    from app.services.agent.stream_session.lazy_session_gate import PendingSessionDraft
    from app.services.agent.streaming_support.stream_collector import StreamContentCollector

logger = logging.getLogger(__name__)


def _unanswered_clarification(session: AgentStreamSession) -> dict[str, object] | None:
    """The clarification card the turn's collector holds while nobody has answered it."""
    extra = session.collector.extra_data
    if not isinstance(extra, dict):
        return None
    clarification = extra.get("clarification")
    if not isinstance(clarification, dict) or clarification.get("answered") is not False:
        return None
    return clarification


def _pending_clarification_interrupt_id(session: AgentStreamSession) -> str | None:
    """The id of the pause the unanswered card was announced for; None when the card carries no usable id."""
    card = _unanswered_clarification(session)
    interrupt_id = card.get(INTERRUPT_ID_KEY) if card else None
    return interrupt_id if isinstance(interrupt_id, str) and interrupt_id else None


def _stopped_at_clarification(session: AgentStreamSession, clarification: ClarificationTimeoutHolder) -> bool:
    """Whether the turn ends at a clarification card nobody has answered."""
    if clarification.pending:
        return True
    return session.request.chat_id is not None and _unanswered_clarification(session) is not None


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


def assistant_turn_payload(
    collector: StreamContentCollector,
    chat_id: str,
    *,
    extra_context: dict[str, object],
    stream_ttft_ms: int | None,
) -> tuple[str, dict[str, object]]:
    """The answer text and the extra data a turn is stored with; citation tags are lifted out of the text.

    The turn a request ran and the one a fired approval timer resumed are stored through this one builder.
    """
    import re

    from myrm_agent_harness.api.hooks import (
        get_memory_runtime_budget,
        get_memory_runtime_injection,
    )

    content = collector.content
    extra_data = dict(collector.extra_data or {})
    if stream_ttft_ms is not None and stream_ttft_ms >= 0:
        extra_data["streamTtftMs"] = stream_ttft_ms
    merge_memory_citation_fallback(extra_data)
    preview = extra_context.get("memory_brief_preview") if isinstance(extra_context, dict) else None
    if isinstance(preview, dict):
        snapshot_id = preview.get("snapshot_id")
        if isinstance(snapshot_id, str) and snapshot_id.strip():
            extra_data["memoryBriefSnapshotId"] = snapshot_id.strip()
    brief_status = extra_context.get("memory_brief_status") if isinstance(extra_context, dict) else None
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

    content, extra_data = assistant_turn_payload(
        session.collector, chat_id, extra_context=session.extra_context, stream_ttft_ms=session.stream_ttft_ms
    )
    await ChatService.persist_assistant_message_safe(
        chat_id,
        content,
        extra_data=extra_data,
        timezone=session.request.timezone,
        sibling_group_id=session.collector.sibling_group_id,
        request_message_id=session.request.message_id,
    )


async def _clear_turn_marker(session: AgentStreamSession) -> None:
    """Remove the replay marker this turn wrote, and only that one (best-effort).

    The chat's next turn replaces the marker with its own row, which a turn that ends late must leave in place; a turn
    that wrote none (a resume) has nothing to remove.
    """
    chat_id = session.request.chat_id
    if not chat_id or session.turn_marker_id is None:
        return
    try:
        await _clear_interrupted_turn_marker(chat_id, marker_id=session.turn_marker_id)
    except Exception as exc:
        logger.warning("Replay marker of a turn was not cleared: chat_id=%s, error=%s", chat_id, exc)


def _arm_pending_interrupt_timeout(session: AgentStreamSession, approval: ApprovalTimeoutHolder) -> None:
    """Arm the timer of the interrupt the turn stopped at, or reopen one that has none."""
    if session.request.chat_id:
        arm_interrupt_timeout(
            session.request.chat_id,
            session.params,
            approval_timeout=approval.value,
            clarification_interrupt_id=_pending_clarification_interrupt_id(session),
            awaiting_answer=session.collector.has_pending_hitl_replay(),
        )


def release_turn_registrations(
    *,
    chat_id: str | None,
    message_id: str | None,
    steering_token: SteeringToken | None,
    goal_provider: GoalProvider | None,
) -> None:
    """Give back what a turn registered for itself: its Stop handle, its steering token and its goal provider.

    The steering token and the goal provider go back by the handle the turn holds, so a turn that ends late leaves the
    entries of the chat's next turn alone.
    """
    if message_id:
        CancellationRegistry.unregister(message_id)
    if not chat_id:
        return
    if steering_token is not None:
        SteeringRegistry.unregister(chat_id, steering_token)
    if goal_provider is not None:
        from app.services.agent.goals.goal_registry import GoalRegistry

        GoalRegistry.unregister(chat_id, goal_provider)


def _release_session_registrations(session: AgentStreamSession) -> None:
    release_turn_registrations(
        chat_id=session.request.chat_id,
        message_id=getattr(session.params, "message_id", None) or getattr(session.request, "message_id", None),
        steering_token=session.steering_token,
        goal_provider=session.goal_provider,
    )


def _release_turn_state(session: AgentStreamSession) -> None:
    """Flush the compaction telemetry and give back what the turn registered."""
    enqueue_context_compaction_telemetry(session.request.chat_id)
    clear_context_task_metrics(session.request.chat_id)
    _release_session_registrations(session)


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
        phase = RunDigestPhase.COMPLETED
        if session.cancel_token.is_cancelled:
            phase = RunDigestPhase.CANCELLED
        elif session.had_fatal_error:
            phase = RunDigestPhase.ERROR
        close_run_digest(
            session.request.chat_id,
            phase=phase,
            progress_steps=list(session.collector._progress_steps),
            agent_id=getattr(session.request, "agent_id", None),
            was_cancelled=session.cancel_token.is_cancelled,
            had_fatal_error=session.had_fatal_error,
            run=session.digest_run,
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

    stopped_at_clarification = _stopped_at_clarification(session, clarification)

    _arm_pending_interrupt_timeout(session, approval)
    schedule_compaction_drain(session.request.chat_id)
    _release_turn_state(session)

    pending_hitl = bool(stopped_at_clarification or approval.value or session.collector.has_pending_hitl_replay())
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
    session.torn_down = True


async def release_unfinished_turn(session: AgentStreamSession) -> None:
    """Tear down a turn whose stream never reached finalize, so that it leaves nothing registered behind.

    Finalize ends a turn that ran. A turn also leaves the turn body without it when a Stop lands while the turn waits
    behind its project's lock (the pump swallows the cancel and returns), when setup or the pump fails, or when the
    task is cancelled. This gives back the registrations and closes the run the way finalize does. A turn the user
    stopped ends as cancelled and takes its replay marker with it; any other turn that ends here did not complete, and
    its marker stays for the crash replay.
    """
    if session.torn_down:
        return
    chat_id = session.request.chat_id
    _release_session_registrations(session)
    session.collector.cleanup()
    stopped = session.cancel_token.is_cancelled
    if not stopped:
        session.had_fatal_error = True
    if session.digest_run is not None:
        try:
            _close_run_digest(session)
        except Exception as exc:
            logger.warning("Run digest of an unfinished turn was not closed: chat_id=%s, error=%s", chat_id, exc)
    if stopped:
        await _clear_turn_marker(session)
    session.torn_down = True


async def _clear_interrupted_turn_marker(chat_id: str, *, marker_id: str) -> None:
    """Remove the write-ahead marker row `marker_id` of the chat, so the marker of the chat's next turn stays."""
    from sqlalchemy import delete

    from app.database.models.chat import InterruptedTurnMarker
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        await db.execute(
            delete(InterruptedTurnMarker).where(
                InterruptedTurnMarker.chat_id == chat_id,
                InterruptedTurnMarker.id == marker_id,
            )
        )
        await db.commit()
