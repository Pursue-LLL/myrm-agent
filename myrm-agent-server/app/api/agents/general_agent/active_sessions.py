"""General Agent API — autonomous decision-making agent with streaming SSE."""

import asyncio
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.infra.limiter import limiter
from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.gateway import get_agent_gateway

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/chat/{chat_id}/attach", response_model=None)
async def attach_to_chat(
    chat_id: str,
    request: Request,
    multiplexed: bool = False,
) -> StreamingResponse | JSONResponse:
    """Attach to an ongoing agent chat session via SSE or fetch snapshot.

    If multiplexed=True, returns a JSONResponse containing the catchup_snapshot
    instead of opening an SSE stream. This is used by the frontend ConnectionManager
    to recover lost data after a network drop without breaking the multiplexed stream.
    """
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access
    from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS

    require_mobile_pair_chat_access(request, chat_id)
    collector = ACTIVE_COLLECTORS.get(chat_id)
    if not collector:
        raise HTTPException(status_code=404, detail="No active task found for this chat in memory")

    if multiplexed:
        # For multiplexed recovery, we just need the snapshot, no need to subscribe to the queue
        snapshot = collector.get_snapshot()
        from app.remote_access.e2ee import e2ee_success_response

        return e2ee_success_response(request, data={"catchup_snapshot": snapshot})

    async def sse_generator() -> AsyncGenerator[str, None]:
        snapshot, q = collector.subscribe()
        logger.info(f"Client attached to chat {chat_id} real-time stream via Collector")

        try:
            # 1. Yield the full snapshot first
            from app.schemas.streaming import SSEEnvelope

            yield SSEEnvelope(type="catchup_snapshot", data=snapshot, message_id=collector.message_id).to_sse_chunk()

            # 2. Yield real-time events
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

                try:
                    # Wait for next event with a small timeout to check for disconnects
                    event = await asyncio.wait_for(q.get(), timeout=2.0)
                    envelope = SSEEnvelope.from_any(event)
                    yield envelope.to_sse_chunk()
                except asyncio.TimeoutError:
                    continue
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
@limiter.limit("30/minute")
async def get_active_sessions(
    request: Request,
) -> JSONResponse:
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
