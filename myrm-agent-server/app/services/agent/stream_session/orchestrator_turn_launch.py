"""Accept phase of the E1 early buffered turn: start the background turn and answer the client.

[INPUT]
- app.services.agent.stream_session.orchestrator_turn_body::execute_agent_turn_after_reserve (POS: the turn itself)
- app.services.agent.stream_session.orchestrator_turn_body::fail_buffered_turn (POS: terminal error SSE + cancel token release)
- app.services.agent.stream_session.session_reservation::ChatSessionReservation (POS: chat reservation handed over to the stream)
- app.services.agent.stream_session.session_reservation::release_unstreamed_reservation (POS: clears a reservation the stream never took over)

[OUTPUT]
- launch_early_buffered_stream: start the turn task, hand the reservation to the stream, return the SSE response or the multiplexed accepted JSON

[POS]
E1 accept phase: the HTTP response leaves here while setup (persist, pre-reply compact, params) still runs in the background task.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.stream_session.orchestrator_turn_body import (
    execute_agent_turn_after_reserve,
    fail_buffered_turn,
)
from app.services.agent.stream_session.session_reservation import ChatSessionReservation, release_unstreamed_reservation
from app.services.agent.stream_session.turn_capability_terminal import (
    TurnCapabilityFailureReason,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry, ResilientStreamBuffer

    from app.services.agent.params import AgentRequest

logger = logging.getLogger(__name__)


async def launch_early_buffered_stream(
    *,
    request: AgentRequest,
    http_request: Request,
    text_content: str,
    stream_started_at_monotonic: float,
    registry: GlobalStreamRegistry,
    buffer: ResilientStreamBuffer,
    session_reservation: ChatSessionReservation,
    record_terminal_failure: Callable[[TurnCapabilityFailureReason], Awaitable[None]],
) -> StreamingResponse | JSONResponse:
    """Start turn execution in background and return stream or multiplexed accepted JSON."""

    async def _background_turn() -> None:
        chat_id_token = None
        agent_id_token = None
        try:
            # 绑定 harness 侧会话上下文：SnapshotObserver 以
            # get_current_chat_id() 作为快照落盘的 session key（.myrm/snapshots/<session>/<msg>.json），
            # 若不设置会 fallback 为 "default"，导致 revert API 按真实 chat_id 查询时永远为空。
            # ContextVar 在 turn task 内生效，覆盖工具调用等整条执行链。
            if request.chat_id:
                from myrm_agent_harness.agent.context_management.infra.session_lock import (
                    reset_current_chat_id,
                    set_current_chat_id,
                )

                chat_id_token = set_current_chat_id(request.chat_id)
            if request.agent_id:
                from app.ai_agents.general_agent.context import (
                    reset_current_agent_id,
                    set_current_agent_id,
                )

                agent_id_token = set_current_agent_id(request.agent_id)
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
            await fail_buffered_turn(
                buffer,
                request.message_id,
                "Stream setup failed",
            )
        finally:
            if chat_id_token is not None:
                try:
                    reset_current_chat_id(chat_id_token)
                except Exception:  # pragma: no cover - context teardown edge
                    pass
            if agent_id_token is not None:
                try:
                    from app.ai_agents.general_agent.context import reset_current_agent_id

                    reset_current_agent_id(agent_id_token)
                except Exception:  # pragma: no cover - context teardown edge
                    pass
            # A reserved chat session that never reached execute_stream (setup
            # failure or cancel before the stream loop) must not leak — release
            # it so the chat is not stuck busy for subsequent turns.
            if request.chat_id:
                release_unstreamed_reservation(request.chat_id, was_resume=request.resume_value is not None)

    task = asyncio.create_task(
        _background_turn(),
        name=f"agent_turn_{request.message_id or 'unknown'}",
    )
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() and t.exception() is not None else None)
    session_reservation.transfer_to_stream()
    if getattr(request, "multiplexed", False):
        return JSONResponse(
            content={"status": "accepted", "message_id": request.message_id},
        )
    return StreamingResponse(
        content=buffer.subscribe(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
