"""Stream exception to user-visible error chunks.

[INPUT]
- app.services.agent.gateway (POS: queue / drain / execution-timeout errors surfaced to the client)
- app.services.agent.stream_session.queue_timeout_error::queue_timeout_error_data (POS: user-facing error payload for a request the concurrency gate refused)
- app.services.agent.stream_session.turn_capability_terminal (POS: records the failed terminal state of a turn that carries capability telemetry)
- app.services.agent.streaming_support.sse_helpers::error_sse (POS: generic SSE error chunk)
- myrm_agent_harness.agent.config.exceptions::ConfigIncompleteError (POS: setup gap with localized user message and resolution steps)
- myrm_agent_harness.toolkits.llms.errors::MyrmLLMError (POS: LLM failure with diagnostic result and recovery actions)

[OUTPUT]
- yield_stream_exception_chunks: turn a stream exception into the user-visible error chunks, mark the turn's collector, and record the failed capability terminal state

[POS]
Error half of the stream pipeline: `stream_chunks` hands it every exception that ends the chunk generator.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.config.exceptions import ConfigIncompleteError
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.utils.runtime.cancellation import CancelReason

from app.schemas.streaming import SSEEnvelope
from app.services.agent.gateway import (
    AgentDrainingError,
    AgentExecutionTimeout,
    AgentQueueTimeout,
)
from app.services.agent.stream_session.queue_timeout_error import queue_timeout_error_data
from app.services.agent.stream_session.turn_capability_terminal import (
    classify_turn_capability_failure_reason,
    record_turn_capability_failed_once,
)
from app.services.agent.streaming_support.sse_helpers import error_sse

if TYPE_CHECKING:
    from app.services.agent.stream_session.stream_session_types import AgentStreamSession

logger = logging.getLogger(__name__)


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
        await record_turn_capability_failed_once(
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
        error_data = queue_timeout_error_data(
            exc,
            session.params.message_id,
            session.params.locale,
        )
        yield SSEEnvelope.from_any(error_data).to_sse_chunk()
        await record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    elif isinstance(exc, AgentDrainingError):
        yield error_sse(
            "Service is restarting, please try again shortly.",
            session.params.message_id,
        )
        await record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    elif isinstance(exc, AgentExecutionTimeout):
        session.had_fatal_error = True
        session.collector.mark_stream_completion_error()
        yield error_sse("Request timed out.", session.params.message_id)
        await record_turn_capability_failed_once(
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
        await record_turn_capability_failed_once(
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
        await record_turn_capability_failed_once(
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
        await record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
    else:
        session.had_fatal_error = True
        session.collector.mark_stream_completion_error()
        logger.error("Agent stream error: %s", exc, exc_info=True)
        yield error_sse("Agent execution error", session.params.message_id)
        await record_turn_capability_failed_once(
            session,
            classify_turn_capability_failure_reason(exc),
        )
