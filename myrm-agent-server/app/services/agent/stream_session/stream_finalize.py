"""Agent stream error handling and session teardown."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator

from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancelReason

from app.schemas.streaming import SSEEnvelope
from app.services.agent.context_compaction_telemetry import enqueue_context_compaction_telemetry
from app.services.agent.gateway import AgentExecutionTimeout, AgentQueueTimeout
from app.services.agent.steering_registry import SteeringRegistry
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
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
        yield error_sse(str(exc) or "Server is busy, please try again later.", session.params.message_id)
    elif isinstance(exc, AgentExecutionTimeout):
        yield error_sse("Request timed out.", session.params.message_id)
    elif isinstance(exc, asyncio.CancelledError):
        logger.warning("Agent cancelled: message_id=%s", session.params.message_id)
        session.cancel_token.cancel(CancelReason.DISCONNECT)
        if session.request.chat_id:
            try:
                from myrm_agent_harness.agent.meta_tools.bash._background_registry import (
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
        logger.warning("Agent is busy (AgentBusyError): message_id=%s", session.params.message_id)
        busy_event = {
            "type": "error",
            "error_type": "AgentBusyError",
            "data": "Agent is busy processing another request for this session.",
            "messageId": session.params.message_id or str(uuid.uuid4()),
            "status_code": 409,
        }
        yield SSEEnvelope.from_any(busy_event).to_sse_chunk()
    elif isinstance(exc, MyrmLLMError):
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
            error_data["retry_after_ms"] = exc.context["cooldown_remaining_ms"]
        yield SSEEnvelope.from_any(error_data).to_sse_chunk()
    else:
        logger.error("Agent stream error: %s", exc, exc_info=True)
        yield error_sse(f"Agent execution error: {exc}", session.params.message_id)


async def finalize_agent_stream_session(
    session: AgentStreamSession,
    token_ctx: object,
    approval: ApprovalTimeoutHolder,
) -> None:
    from myrm_agent_harness.agent.security import user_credentials_ctx

    user_credentials_ctx.reset(token_ctx)
    if session.collector.has_content and session.request.chat_id:
        import asyncio
        import re

        from myrm_agent_harness.agent._skill_agent_context import get_memory_manager

        from app.services.chat.chat_service import ChatService

        content = session.collector.content
        extra_data = session.collector.extra_data or {}
        
        # Parse and strip citations
        citations = list(set(re.findall(r"<cite:([^>]+)>", content)))
        if citations:
            content = re.sub(r"<cite:[^>]+>", "", content)
            extra_data["citations"] = citations
            
            try:
                manager = get_memory_manager()
                if manager:
                    if citations and hasattr(manager, "record_citations"):
                        asyncio.create_task(manager.record_citations(citations))
                    if hasattr(manager, "_last_budget"):
                        extra_data["memoryBudget"] = manager._last_budget
            except Exception as e:
                logger.warning("Failed to process memory hooks in finalize: %s", e)

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
    session.collector.cleanup()

