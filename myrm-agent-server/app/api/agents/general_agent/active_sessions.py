"""General Agent API — autonomous decision-making agent with streaming SSE."""

import asyncio
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from myrm_agent_harness.agent.streaming.stream_buffer import HEARTBEAT_FRAME, HEARTBEAT_INTERVAL_SEC

from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.gateway import get_agent_gateway

logger = logging.getLogger(__name__)

router = APIRouter()

# How often an attach stream looks up whether its client left or its turn ended while no event arrives.
_DISCONNECT_POLL_SEC = 2.0


@router.get("/chat/{chat_id}/attach", response_model=None)
async def attach_to_chat(
    chat_id: str,
    request: Request,
    multiplexed: bool = False,
) -> StreamingResponse | JSONResponse:
    """Attach to an ongoing agent chat session via SSE or fetch its snapshot.

    The stream sends ``HEARTBEAT_FRAME`` whenever the turn has been quiet for ``HEARTBEAT_INTERVAL_SEC``, like the
    run's own stream does: the page's stream consumer reads a stream that carries no frame for three intervals as a
    dead connection, however long the turn itself is silent.

    If multiplexed=True, returns a JSONResponse containing the catchup_snapshot instead of
    opening an SSE stream, so a client can refresh many chats without holding a connection per chat.
    """
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access
    from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS

    require_mobile_pair_chat_access(request, chat_id)
    collector = ACTIVE_COLLECTORS.get(chat_id)
    if not collector:
        raise HTTPException(status_code=404, detail="No active task found for this chat in memory")

    if multiplexed:
        # Snapshot only: no subscription to the collector queue is held.
        snapshot = collector.get_snapshot()
        from app.remote_access.e2ee import e2ee_success_response

        return e2ee_success_response(request, data={"catchup_snapshot": snapshot})

    async def sse_generator() -> AsyncGenerator[str, None]:
        snapshot, q = collector.subscribe()
        logger.info(f"Client attached to chat {chat_id} real-time stream via Collector")

        try:
            # 1. Yield the full snapshot first
            from app.schemas.streaming import SSEEnvelope

            yield SSEEnvelope(type="catchup_snapshot", data=snapshot, messageId=collector.message_id).to_sse_chunk()

            # 2. Yield real-time events; a quiet turn gets the keep-alive frame
            quiet_since = time.monotonic()
            while True:
                if await request.is_disconnected():
                    break

                # Collector 已从 ACTIVE_COLLECTORS 移除意味着 turn 已正常结束
                # （含无 pending HITL 时 finalize 调用的 cleanup）。若此时仍保持
                # 长连接，前端 consumeStream 将永远读不到流结束，attachToChat 的
                # loading 复位永不执行。检测到 collector 注销后主动终止 attach 流。
                if ACTIVE_COLLECTORS.get(chat_id) is not collector:
                    logger.info(
                        "Collector for chat %s no longer active, ending attach stream",
                        chat_id,
                    )
                    break

                # Wake in time for the keep-alive frame, and at least every poll to notice a departed client or a finished turn.
                until_keep_alive = max(HEARTBEAT_INTERVAL_SEC - (time.monotonic() - quiet_since), 0.0)
                try:
                    event = await asyncio.wait_for(q.get(), timeout=min(_DISCONNECT_POLL_SEC, until_keep_alive))
                except asyncio.TimeoutError:
                    if time.monotonic() - quiet_since < HEARTBEAT_INTERVAL_SEC:
                        continue
                    chunk = HEARTBEAT_FRAME
                else:
                    chunk = SSEEnvelope.from_any(event).to_sse_chunk()
                yield chunk
                quiet_since = time.monotonic()
        finally:
            collector.unsubscribe(q)
            logger.info(f"Client detached from chat {chat_id} real-time stream")

    from app.remote_access.e2ee import encrypt_sse_stream, get_request_e2ee_session

    e2ee_session = get_request_e2ee_session(request)
    stream = sse_generator()
    if e2ee_session is not None:
        stream = encrypt_sse_stream(stream, e2ee_session)

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


@router.get("/active-sessions")
async def get_active_sessions() -> JSONResponse:
    """Get active agent sessions for Multi-Pane status overview.

    Returns running sessions and available concurrent execution slots.
    """
    from app.core.utils.response_utils import success_response

    gateway = get_agent_gateway()
    return success_response(
        data={
            "activeSessions": gateway.get_active_sessions(),
            "maxConcurrent": gateway.config.max_per_user,
            "availableSlots": gateway.get_available_slots(),
        }
    )


@router.get("/chat/{chat_id}/turn-state")
async def get_chat_turn_state(chat_id: str, request: Request) -> JSONResponse:
    """What the server still holds for one chat: a running turn, or one parked behind a tool-approval card.

    A parked turn has released its gateway session, yet its collector still holds the card that a reloaded page can get back
    through attach. A tool-approval card has no stored record (a clarification is stored with the message, an
    ``approval_required`` card has its registry record), so only the collector can hand it back.

    The state is read per chat, not from the global session list, so a phone paired to this chat alone can ask for it.
    The two flags are not secret and the page reads them with the shared ``apiRequest``, which never decrypts, so the
    answer is plain JSON even when the request carries an E2EE session.
    """
    from app.core.utils.response_utils import success_response
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access
    from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS

    require_mobile_pair_chat_access(request, chat_id)
    collector = ACTIVE_COLLECTORS.get(chat_id)
    return success_response(
        data={
            "running": get_agent_gateway().is_session_active(chat_id),
            "awaitingApproval": collector is not None and collector.has_pending_tool_approval(),
        }
    )
