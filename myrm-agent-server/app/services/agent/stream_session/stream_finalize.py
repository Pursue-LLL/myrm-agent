"""Agent stream error handling and session teardown."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator

from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationRegistry,
    CancelReason,
)

from app.schemas.streaming import SSEEnvelope
from app.services.agent.context_compaction_telemetry import (
    enqueue_context_compaction_telemetry,
)
from app.services.agent.gateway import AgentExecutionTimeout, AgentQueueTimeout
from app.services.agent.memory_brief_telemetry import (
    enqueue_memory_brief_status_telemetry,
)
from app.services.agent.steering_registry import SteeringRegistry
from app.services.agent.stream_session._memory_status_helpers import (
    build_memory_brief_status_payload,
    observe_memory_brief_status_payload,
)
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.citation_persistence import (
    merge_memory_citation_fallback,
)
from app.services.agent.streaming_support.sse_helpers import (
    clear_context_task_metrics,
    error_sse,
    schedule_approval_timeout,
)

logger = logging.getLogger(__name__)


async def yield_stream_exception_chunks(
    session: AgentStreamSession,
    exc: BaseException,
) -> AsyncGenerator[str, None]:
    if isinstance(exc, ValueError):
        error_msg = str(exc)
        if "Resume failed" in error_msg or "context overflow" in error_msg:
            session.had_fatal_error = True
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
    elif isinstance(exc, AgentQueueTimeout):
        yield error_sse(
            str(exc) or "Server is busy, please try again later.",
            session.params.message_id,
        )
    elif isinstance(exc, AgentExecutionTimeout):
        session.had_fatal_error = True
        yield error_sse("Request timed out.", session.params.message_id)
    elif isinstance(exc, asyncio.CancelledError):
        logger.warning("Agent cancelled: message_id=%s", session.params.message_id)
        session.cancel_token.cancel(CancelReason.DISCONNECT)
        if session.request.chat_id:
            try:
                from myrm_agent_harness.api.hooks import (
                    get_background_registry,
                )

                killed = await get_background_registry().kill_session_jobs(
                    session.request.chat_id
                )
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
    elif type(exc).__name__ == "AgentBusyError":
        logger.warning(
            "Agent is busy (AgentBusyError): message_id=%s", session.params.message_id
        )
        busy_event = {
            "type": "error",
            "error_type": "AgentBusyError",
            "data": "Agent is busy processing another request for this session.",
            "messageId": session.params.message_id or str(uuid.uuid4()),
            "status_code": 409,
        }
        yield SSEEnvelope.from_any(busy_event).to_sse_chunk()
    elif isinstance(exc, MyrmLLMError):
        session.had_fatal_error = True
        logger.error("Agent LLM error: %s", exc)
        lang = session.params.locale or "en"
        from app.core.errors.llm_errors import generate_recovery_actions

        diagnostic_result = exc.diagnostic_result or {}
        recovery_actions = generate_recovery_actions(exc.error_code, lang)
        error_type = (
            exc.error_code.name
            if hasattr(exc.error_code, "name")
            else str(exc.error_code)
        )
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
            error_data["retry_after_ms"] = exc.context["cooldown_remaining_ms"]
        yield SSEEnvelope.from_any(error_data).to_sse_chunk()
    else:
        session.had_fatal_error = True
        logger.error("Agent stream error: %s", exc, exc_info=True)
        yield error_sse(f"Agent execution error: {exc}", session.params.message_id)


async def finalize_agent_stream_session(
    session: AgentStreamSession,
    token_ctx: object,
    approval: ApprovalTimeoutHolder,
) -> None:
    from myrm_agent_harness.agent.security import user_credentials_ctx

    user_credentials_ctx.reset(token_ctx)
    if session.collector.has_persistable_turn and session.request.chat_id:
        import asyncio
        import re

        from myrm_agent_harness.api.hooks import (
            get_memory_manager,
            get_memory_runtime_budget,
            get_memory_runtime_injection,
        )

        from app.services.chat.chat_service import ChatService

        content = session.collector.content
        extra_data = dict(session.collector.extra_data or {})
        merge_memory_citation_fallback(extra_data)
        preview = (
            session.extra_context.get("memory_brief_preview")
            if isinstance(session.extra_context, dict)
            else None
        )
        if isinstance(preview, dict):
            snapshot_id = preview.get("snapshot_id")
            if isinstance(snapshot_id, str) and snapshot_id.strip():
                extra_data["memoryBriefSnapshotId"] = snapshot_id.strip()
        brief_status = (
            session.extra_context.get("memory_brief_status")
            if isinstance(session.extra_context, dict)
            else None
        )
        # Parse and strip citations
        citations = list(dict.fromkeys(re.findall(r"<cite:([^>]+)>", content)))
        if citations:
            content = re.sub(r"<cite:[^>]+>", "", content)
            extra_data["citations"] = citations

        injection: dict[str, str] | None = None
        manager = None
        if citations:
            try:
                manager = get_memory_manager()
            except Exception as e:
                logger.warning("Failed to resolve memory manager in finalize: %s", e)
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
        if citations and manager and hasattr(manager, "record_citations"):
            asyncio.create_task(manager.record_citations(citations))
        status_payload = build_memory_brief_status_payload(brief_status, injection)
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
        )

    if approval.value and session.request.chat_id:
        schedule_approval_timeout(
            chat_id=session.request.chat_id,
            timeout_info=approval.value,
            params=session.params,
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
    await session.monitor.stop()
    CancellationRegistry.unregister(session.params.message_id)
    if session.request.chat_id:
        SteeringRegistry.unregister(session.request.chat_id)
        from app.services.agent.goal_registry import GoalRegistry

        GoalRegistry.unregister(session.request.chat_id)

    if (
        session.collector.has_content
        and session.request.chat_id
        and not session.cancel_token.is_cancelled
    ):
        try:
            from app.services.agent.evolution.engine import trigger_skill_evolution

            tool_steps = len(session.collector._progress_steps)
            dw_text: str | None = None
            if session.request.use_workflow and session.collector.content:
                dw_text = session.collector.content

            trigger_skill_evolution(
                chat_id=session.request.chat_id,
                model_cfg=session.params.model_cfg,
                tool_steps_count=tool_steps,
                conversation_text=dw_text,
                agent_id=getattr(session.request, "agent_id", None),
            )
        except Exception as evo_exc:
            logger.debug("Skill evolution trigger skipped: %s", evo_exc)

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
                remaining = evo_integration._slice_cursors.pop(
                    session.request.chat_id, None
                )
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

    if session.request.chat_id and session.collector.cross_turn_data_updates:
        from app.services.chat.ui_artifact_patch import patch_ui_artifact_data_updates

        await patch_ui_artifact_data_updates(
            session.request.chat_id,
            session.collector.cross_turn_data_updates,
        )

    session.collector.cleanup()
