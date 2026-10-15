"""Agent stream error handling and session teardown.

[INPUT]
- app.services.agent.streaming_support.hitl_timeout::arm_interrupt_timeout (POS: arms or reopens the timer of the interrupt the turn stopped at)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: persisted turn content)
- app.services.agent.gateway (POS: queue / drain / execution-timeout errors surfaced to the client)
- myrm_agent_harness.utils.runtime.cancellation::CancellationRegistry (POS: Stop handle, unregistered when the turn ends)

[OUTPUT]
- yield_stream_exception_chunks: turn a stream exception into the user-visible error chunks
- finalize_agent_stream_session: persist the turn, record its terminal state, arm the HITL timeout of a pending interrupt and release the turn's session state

[POS]
Teardown half of the stream pipeline: runs once per turn after the chunk generator ends, however it ended.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from contextvars import Token

from myrm_agent_harness.agent.config.exceptions import ConfigIncompleteError
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase
from myrm_agent_harness.core.security.types import EphemeralUserCredential, user_credentials_ctx
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationRegistry,
    CancelReason,
)

from app.schemas.streaming import SSEEnvelope
from app.services.agent.context_compaction_telemetry import (
    enqueue_context_compaction_telemetry,
)
from app.services.agent.gateway import (
    AgentDrainingError,
    AgentExecutionTimeout,
    AgentQueueTimeout,
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
from app.services.agent.stream_session.migration_readiness_anchor import (
    record_migration_first_turn_outcome,
)
from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    ClarificationTimeoutHolder,
)
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.stream_session.turn_capability_terminal import (
    TurnCapabilityFailureReason,
    classify_turn_capability_failure_reason,
    has_turn_capability_terminal_context,
    record_turn_capability_send_completed,
    record_turn_capability_send_failed,
)
from app.services.agent.streaming_support.citation_persistence import (
    merge_memory_citation_fallback,
)
from app.services.agent.streaming_support.hitl_timeout import (
    arm_interrupt_timeout,
    mark_pending_clarification_answered,
    mark_pending_directory_request_answered,
)
from app.services.agent.streaming_support.sse_helpers import (
    clear_context_task_metrics,
    error_sse,
)

logger = logging.getLogger(__name__)


def _collector_has_unanswered_clarification(session: AgentStreamSession) -> bool:
    extra = session.collector.extra_data
    if not isinstance(extra, dict):
        return False
    clarification = extra.get("clarification")
    if not isinstance(clarification, dict):
        return False
    return clarification.get("answered") is False


def _collector_has_unanswered_directory_request(session: AgentStreamSession) -> bool:
    extra = session.collector.extra_data
    if not isinstance(extra, dict):
        return False
    directory_request = extra.get("directoryRequest")
    if not isinstance(directory_request, dict):
        return False
    return directory_request.get("answered") is False


def _directory_timeout_needed(
    session: AgentStreamSession,
    clarification: ClarificationTimeoutHolder,
) -> bool:
    if clarification.directory_pending:
        return True
    if session.request.chat_id is None:
        return False
    return _collector_has_unanswered_directory_request(session)


def _clarification_timeout_needed(
    session: AgentStreamSession,
    clarification: ClarificationTimeoutHolder,
) -> bool:
    if clarification.pending:
        return True
    if session.request.chat_id is None:
        return False
    return _collector_has_unanswered_clarification(session)


async def _record_turn_capability_failed_once(
    session: AgentStreamSession,
    reason: TurnCapabilityFailureReason,
) -> None:
    if session.turn_capability_terminal_recorded or not has_turn_capability_terminal_context(session.request):
        return
    recorded = await record_turn_capability_send_failed(
        session.request,
        reason,
    )
    if recorded:
        session.turn_capability_terminal_recorded = True


async def _record_turn_capability_completed_once(
    session: AgentStreamSession,
) -> None:
    if session.turn_capability_terminal_recorded or not has_turn_capability_terminal_context(session.request):
        return
    recorded = await record_turn_capability_send_completed(session.request)
    if recorded:
        session.turn_capability_terminal_recorded = True


def _queue_timeout_error_data(
    exc: AgentQueueTimeout,
    message_id: str | None,
    locale: str | None,
) -> dict[str, object]:
    """Build a structured, user-facing error for AgentQueueTimeout.

    Distinguishes the three concurrency-limit causes and names the current
    holders so the message stays actionable (mirrors Hermes' limit message).
    """
    lang = "zh" if (locale or "en").startswith("zh") else "en"
    holders = exc.active_sessions
    holder_summary = ""
    if holders:
        names = [f"{h.get('chatId', h.get('agentType', 'session'))} ({h.get('agentType', 'agent')})" for h in holders[:3]]
        if len(holders) > 3:
            extra = len(holders) - 3
            names.append(f"等 {extra} 个会话" if lang == "zh" else f"+{extra} more")
        holder_summary = f" 当前占用：{'、'.join(names)}。" if lang == "zh" else f" Held by: {', '.join(names)}."

    if exc.reason == "memory_pressure":
        user_message = (
            "服务内存压力过高，已暂停接收新任务，请稍后重试。"
            if lang == "zh"
            else "Server memory pressure is high and new tasks are paused. Please retry shortly."
        )
        resolution_steps = (
            ["等待内存压力缓解后重试", "若持续出现，请关闭其他占用内存的程序"]
            if lang == "zh"
            else [
                "Wait for memory pressure to ease and retry",
                "If it persists, close other memory-heavy programs",
            ]
        )
    elif exc.reason == "user_limit":
        user_message = (
            f"并发会话已达上限，无法接收新请求。{holder_summary}请先结束部分运行中的任务后重试。"
            if lang == "zh"
            else (
                f"Concurrency limit reached; the request could not be accepted."
                f"{holder_summary} Please finish or stop some running tasks and retry."
            )
        )
        resolution_steps = (
            ["前往工作台查看并结束运行中的会话", "等待已有任务完成后重试"]
            if lang == "zh"
            else [
                "Open the workspace and stop running sessions",
                "Wait for an active task to finish and retry",
            ]
        )
    else:
        user_message = (
            f"服务繁忙，无法接收新请求。{holder_summary}请稍后重试。"
            if lang == "zh"
            else f"Server is busy; the request could not be accepted.{holder_summary} Please retry shortly."
        )
        resolution_steps = (
            ["稍后重试", "若持续出现，请检查是否有较多并发任务"]
            if lang == "zh"
            else [
                "Retry shortly",
                "If it persists, check whether too many tasks are running",
            ]
        )

    return {
        "type": "error",
        "error_kind": "concurrency_limit",
        "data": user_message,
        "messageId": message_id or str(uuid.uuid4()),
        "diagnostic_result": {
            "error_type": "concurrency_limit",
            "user_message": user_message,
            "resolution_steps": resolution_steps,
            "locale": lang,
        },
        "metadata": {
            "error_type": "concurrency_limit",
            "reason": exc.reason,
        },
    }


async def yield_stream_exception_chunks(
    session: AgentStreamSession,
    exc: BaseException,
) -> AsyncGenerator[str, None]:
    if isinstance(exc, ValueError):
        error_msg = str(exc)
        if "Resume failed" in error_msg or "context overflow" in error_msg:
            session.had_fatal_error = True
            session.collector.mark_stream_completion_error()
            logger.error("Resume validation failed: %s", error_msg)
            if session.request.chat_id:
                try:
                    from app.platform_utils import get_checkpointer

                    cp = get_checkpointer()
                    chat_id = session.request.chat_id
                    for tid in (chat_id, f"chat_{chat_id}"):
                        await cp.adelete_thread(tid)
                    logger.info(
                        "Checkpoint cleared after Resume failure: chat_id=%s",
                        chat_id,
                    )
                except Exception as cleanup_error:
                    logger.warning(
                        "Checkpoint cleanup failed (non-blocking): %s",
                        cleanup_error,
                    )
            yield error_sse(f"Resume failed: {error_msg}", session.params.message_id)
        else:
            yield error_sse(f"Agent error: {error_msg}", session.params.message_id)
        await _record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    elif isinstance(exc, AgentQueueTimeout):
        session.had_fatal_error = True
        session.collector.mark_stream_completion_error()
        logger.warning(
            "Agent queue timeout: message_id=%s reason=%s holders=%d",
            session.params.message_id,
            exc.reason,
            len(exc.active_sessions),
        )
        error_data = _queue_timeout_error_data(
            exc,
            session.params.message_id,
            session.params.locale,
        )
        yield SSEEnvelope.from_any(error_data).to_sse_chunk()
        await _record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    elif isinstance(exc, AgentDrainingError):
        yield error_sse(
            "Service is restarting, please try again shortly.",
            session.params.message_id,
        )
        await _record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    elif isinstance(exc, AgentExecutionTimeout):
        session.had_fatal_error = True
        session.collector.mark_stream_completion_error()
        yield error_sse("Request timed out.", session.params.message_id)
        await _record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    elif isinstance(exc, asyncio.CancelledError):
        logger.warning("Agent cancelled: message_id=%s", session.params.message_id)
        session.cancel_token.cancel(CancelReason.DISCONNECT)
        session.collector._completion_status = "cancelled"
        if session.request.chat_id:
            try:
                from myrm_agent_harness.api.hooks import (
                    get_background_registry,
                )

                killed = await get_background_registry().kill_session_jobs(session.request.chat_id)
                if killed:
                    logger.info(
                        "CancelledError path killed %d background job(s) for chat_id=%s",
                        killed,
                        session.request.chat_id,
                    )
            except Exception as bg_exc:
                logger.warning(
                    "Failed to kill background jobs on CancelledError for chat_id=%s: %s",
                    session.request.chat_id,
                    bg_exc,
                )
        await _record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    elif type(exc).__name__ == "AgentBusyError":
        logger.warning("Agent is busy (AgentBusyError): message_id=%s", session.params.message_id)
        busy_event = {
            "type": "error",
            "error_type": "AgentBusyError",
            "data": "Agent is busy processing another request for this session.",
            "messageId": session.params.message_id or str(uuid.uuid4()),
            "status_code": 409,
        }
        yield SSEEnvelope.from_any(busy_event).to_sse_chunk()
    elif isinstance(exc, ConfigIncompleteError):
        session.had_fatal_error = True
        session.collector.mark_stream_completion_error()
        raw_locale = session.params.locale or "en"
        base_locale = raw_locale.split("-")[0].lower()
        user_message = (
            exc.user_friendly_message.get(raw_locale)
            or exc.user_friendly_message.get(base_locale)
            or exc.user_friendly_message.get("en", str(exc))
        )
        error_data = {
            "type": "error",
            "data": user_message,
            "messageId": session.params.message_id or str(uuid.uuid4()),
            "metadata": {
                "error_type": exc.error_code,
                "resolution_steps": exc.resolution_steps,
            },
        }
        yield SSEEnvelope.from_any(error_data).to_sse_chunk()
        await _record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    elif isinstance(exc, MyrmLLMError):
        session.had_fatal_error = True
        session.collector.mark_stream_completion_error()
        logger.error("Agent LLM error: %s", exc)
        lang = session.params.locale or "en"
        from app.core.errors.llm_errors import generate_recovery_actions

        diagnostic_result = exc.diagnostic_result or {}
        recovery_actions = generate_recovery_actions(exc.error_code, lang)
        error_type = exc.error_code.name if hasattr(exc.error_code, "name") else str(exc.error_code)
        error_data = {
            "type": "error",
            "data": diagnostic_result.get("user_message", str(exc)),
            "messageId": session.params.message_id or str(uuid.uuid4()),
            "diagnostic_result": diagnostic_result,
            "recovery_actions": recovery_actions,
            "metadata": {
                "error_type": error_type,
                "recovery_actions": recovery_actions,
            },
        }
        if exc.context and "cooldown_remaining_ms" in exc.context:
            error_data["cooldown_remaining_ms"] = exc.context["cooldown_remaining_ms"]
        yield SSEEnvelope.from_any(error_data).to_sse_chunk()
        await _record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    else:
        session.had_fatal_error = True
        session.collector.mark_stream_completion_error()
        logger.error("Agent stream error: %s", exc, exc_info=True)
        yield error_sse("Agent execution error", session.params.message_id)
        await _record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )


async def finalize_agent_stream_session(
    session: AgentStreamSession,
    token_ctx: Token[tuple[EphemeralUserCredential, ...]],
    approval: ApprovalTimeoutHolder,
    clarification: ClarificationTimeoutHolder,
) -> None:
    user_credentials_ctx.reset(token_ctx)
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

    if session.collector.has_persistable_turn and session.request.chat_id and (draft is None or draft.committed):
        import re

        from myrm_agent_harness.api.hooks import (
            get_memory_runtime_budget,
            get_memory_runtime_injection,
        )

        from app.services.chat.chat_service import ChatService

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
            session.request.chat_id,
        )
        if status_payload is not None:
            extra_data["memoryBriefStatus"] = status_payload
            observe_memory_brief_status_payload(phase="persist", payload=status_payload)
            enqueue_memory_brief_status_telemetry(
                phase="persist",
                payload=status_payload,
            )

        await ChatService.persist_assistant_message_safe(
            session.request.chat_id,
            content,
            extra_data=extra_data,
            timezone=session.request.timezone,
            sibling_group_id=session.collector.sibling_group_id,
            request_message_id=session.request.message_id,
        )

    # Clear crash auto-continue marker on normal completion (best-effort)
    if session.request.chat_id:
        try:
            await _clear_interrupted_turn_marker(session.request.chat_id)
        except Exception as marker_exc:
            logger.debug("Turn marker cleanup skipped: %s", marker_exc)

    await record_migration_first_turn_outcome(
        request=session.request,
        had_fatal_error=session.had_fatal_error,
        has_assistant_content=session.collector.has_content,
        live_readiness_status=session.migration_live_readiness_status,
    )

    if session.request.chat_id:
        extra = session.collector.extra_data
        collector_clarification = extra.get("clarification") if isinstance(extra, dict) else None
        collector_clarification_answered = (
            isinstance(collector_clarification, dict) and collector_clarification.get("answered") is True
        )
        resume_completed = session.request.resume_value is not None and not clarification.pending
        if resume_completed or collector_clarification_answered:
            await mark_pending_clarification_answered(session.request.chat_id)
            await mark_pending_directory_request_answered(session.request.chat_id)

    clarification_sched_needed = _clarification_timeout_needed(session, clarification)
    directory_sched_needed = _directory_timeout_needed(session, clarification)

    if session.request.chat_id:
        arm_interrupt_timeout(
            session.request.chat_id,
            session.params,
            approval_timeout=approval.value,
            clarification_pending=clarification_sched_needed,
            directory_pending=directory_sched_needed,
            awaiting_answer=session.collector.has_pending_hitl_replay(),
        )

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

    enqueue_context_compaction_telemetry(session.request.chat_id)
    clear_context_task_metrics(session.request.chat_id)
    target_msg_id = getattr(session.params, "message_id", None) or getattr(session.request, "message_id", None)
    if target_msg_id:
        CancellationRegistry.unregister(target_msg_id)
    if session.request.chat_id:
        SteeringRegistry.unregister(session.request.chat_id)
        from app.services.agent.goals.goal_registry import GoalRegistry

        GoalRegistry.unregister(session.request.chat_id)

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

    pending_hitl = bool(
        clarification_sched_needed
        or (approval.value and not clarification_sched_needed)
        or session.collector.has_pending_hitl_replay()
    )
    if not pending_hitl and has_turn_capability_terminal_context(session.request):
        if session.cancel_token.is_cancelled:
            await _record_turn_capability_failed_once(session, "abort")
        elif session.had_fatal_error or not session.collector.has_content:
            await _record_turn_capability_failed_once(session, "unknown_error")
        else:
            await _record_turn_capability_completed_once(session)

    if pending_hitl:
        logger.info(
            "Deferring collector cleanup for pending HITL: chat_id=%s",
            session.request.chat_id,
        )
    else:
        if session.request.chat_id:
            from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

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
