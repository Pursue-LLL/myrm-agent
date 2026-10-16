"""Agent stream session orchestrator — business flow for General Agent SSE.

[INPUT]
- app.services.agent.params (POS: request conversion)
- app.services.agent.stream_session.orchestrator_turn_launch (POS: E1 accept phase, starts the background turn and answers the client)
- app.services.agent.stream_session.orchestrator_turn_body (POS: write-ahead interrupted-turn marker written by the turn)
- myrm_agent_harness.agent.middlewares.approval.scheduler::ApprovalTimeoutScheduler (POS: first-resolver arbitration between the approval timeout timer and a manual resume)

[OUTPUT]
- run_agent_stream: validation + reserve + already-resolved resume refusal (HTTP 409) + early StreamingResponse | JSONResponse

[POS]
Service-layer stream orchestration entry. Pre-reserve validation stays synchronous; post-reserve turn runs in the background (`orchestrator_turn_launch` starts it, `orchestrator_turn_body` is the turn) so clients receive live SSE during pre-reply compact.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams

from fastapi.responses import JSONResponse, StreamingResponse
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.params import (
    AgentRequest,
    ArchiveRestoreRequestError,
    prevalidate_archive_restore_actions,
)
from app.services.agent.runtime_context import prefer_direct_agent_stream
from app.services.agent.stream_session.chat_history_bootstrap import stream_text_content
from app.services.agent.stream_session.reconnect import try_stream_reconnect
from app.services.agent.stream_session.risk_gate import check_stream_risk, resume_typed_texts
from app.services.agent.stream_session.session_reservation import ChatSessionReservation
from app.services.agent.stream_session.stream_busy import agent_busy_streaming_response
from app.services.agent.stream_session.stream_lane_factory import (
    archive_restore_error_response,
)
from app.services.agent.stream_session.turn_capability_terminal import (
    TurnCapabilityFailureReason,
    has_turn_capability_terminal_context,
    record_turn_capability_send_failed,
)

logger = logging.getLogger(__name__)

_ACTION_MODE_FEATURE_GATE: dict[str, str] = {
    "deep_research": "deep_research",
}


# Gateway hygiene limit: ~120K tokens (rough character-to-token ratio) to prevent OOM
_GATEWAY_MAX_INPUT_CHARS: int = 360_000


async def _count_pending_approvals(chat_id: str) -> int:
    """Return the number of pending HITL approvals for a chat.

    Used by the gateway to reject new runs while the previous turn is waiting
    on human approval, so queued messages do not trample the pending collector
    or block an eventual approval resume behind chat-level mutual exclusion.

    Fails open: if the approval store cannot be reached the run is allowed to
    proceed, because the gate is an ordering enhancement and must never become
    a single point of failure for normal messages.
    """
    try:
        from app.services.approvals.registry import ApprovalRegistry

        return await ApprovalRegistry.count_pending_for_chat(chat_id)
    except Exception as exc:
        logger.warning(
            "Pending approval gate skipped (approval store unavailable): chat_id=%s err=%s",
            chat_id,
            exc,
        )
        return 0


def _reject_legacy_consensus_request(request: AgentRequest) -> JSONResponse | None:
    """Reject removed consensus action_mode with a clear migration hint."""
    if request.action_mode != "consensus":
        return None
    return JSONResponse(
        status_code=400,
        content={
            "detail": ("action_mode 'consensus' was removed. Use action_mode 'agent' with active_moa_preset_id instead."),
        },
    )


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
    consensus_rejection = _reject_legacy_consensus_request(request)
    if consensus_rejection is not None:
        return consensus_rejection

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
                content={"detail": f"{request.action_mode} is disabled via Feature Gate"},
            )

    text_content = stream_text_content(request)

    # The risk gate reads what the user typed: the spill below replaces a long paste with a stub that hides its contents.
    # The regeneration guidance is typed too and becomes a system-level instruction, so it is screened on its own; it
    # stays out of text_content, which the spill and the size check below read and may write back into the query. A
    # resumed run has no query: what the user typed is the reason or guidance of an approval answer.
    typed_texts: Sequence[str | None] = (
        (text_content, request.regenerate_instruction)
        if request.resume_value is None
        else resume_typed_texts(request.resume_value)
    )
    for typed in typed_texts:
        risk_block = await check_stream_risk(typed, request.chat_id)
        if risk_block is not None:
            await _record_terminal_failure_if_needed("risk_held")
            return risk_block

    # Context Guard Ingress defense: transparently spill oversized prompts to sandbox workspace
    try:
        from app.services.agent.context_guard_service import ContextGuardService

        guard_res = await ContextGuardService.guard_inbound_prompt(
            chat_id=request.chat_id,
            raw_prompt=text_content,
            role="user",
        )
        if guard_res.spilled:
            logger.info(
                "ContextGuard mitigated large prompt for chat_id=%s message_id=%s (%d chars -> spilled file)",
                request.chat_id,
                request.message_id,
                guard_res.original_char_count,
            )
            text_content = guard_res.sanitized_content
            # Update in-memory request query string/content
            if isinstance(request.query, str):
                request.query = text_content
    except Exception as guard_exc:
        logger.warning("ContextGuard check encountered non-fatal error: %s", guard_exc)

    # Gateway hygiene check: block massive malicious payloads before they hit the agent harness
    if len(text_content) > _GATEWAY_MAX_INPUT_CHARS:
        logger.warning(f"Gateway rejected massive payload: length={len(text_content)} chars")
        await _record_terminal_failure_if_needed("server_error")
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Request exceeds gateway token limits (approx 120K tokens). Please reduce the size of your input."
            },
        )

    if request.resume_value is None:
        try:
            await prevalidate_archive_restore_actions(request)
        except ArchiveRestoreRequestError as exc:
            await _record_terminal_failure_if_needed("archive_restore_invalid")
            return archive_restore_error_response(exc)

        if request.chat_id:
            pending_count = await _count_pending_approvals(request.chat_id)
            if pending_count > 0:
                logger.info(
                    "Gateway rejected new run while HITL approvals pending: chat_id=%s pending=%d",
                    request.chat_id,
                    pending_count,
                )
                return agent_busy_streaming_response(request.message_id)

    session_reservation = ChatSessionReservation()
    try:
        busy_error = session_reservation.try_reserve(
            request.chat_id,
            message_id=request.message_id,
        )
        if busy_error is not None:
            return agent_busy_streaming_response(request.message_id)

        # The harness timer and this manual resume race for one approval; the loser must not run the turn again.
        # Refused here, before the response is accepted, so the client gets a status code it can act on.
        if request.resume_value is not None and request.chat_id:
            if not ApprovalTimeoutScheduler.get().resolve_if_first(request.chat_id):
                logger.warning("Resume rejected (timeout already resolved): chat_id=%s", request.chat_id)
                await _record_terminal_failure_if_needed("unknown_error")
                return JSONResponse(
                    status_code=409,
                    content={"detail": "This approval has already been resolved by timeout."},
                )

        buffer = await registry.get_or_create(request.message_id)
        from app.services.agent.stream_session.orchestrator_turn_launch import (
            launch_early_buffered_stream,
        )

        return await launch_early_buffered_stream(
            request=request,
            http_request=http_request,
            text_content=text_content,
            stream_started_at_monotonic=stream_started_at_monotonic,
            registry=registry,
            buffer=buffer,
            session_reservation=session_reservation,
            record_terminal_failure=_record_terminal_failure_if_needed,
        )
    finally:
        session_reservation.release()


async def _write_interrupted_turn_marker(
    request: AgentRequest,
    params: GeneralAgentParams,
) -> None:
    """Persist a write-ahead marker so a crash leaves a recoverable trace."""
    from app.services.agent.stream_session.orchestrator_turn_body import (
        write_interrupted_turn_marker,
    )

    await write_interrupted_turn_marker(request, params)
