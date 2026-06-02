"""WebSocket Evolution Proposal Streaming — HTTP transport only."""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.infra.ws_origin_guard import verify_ws_origin
from app.services.skills.ws_hub import (
    broadcast_proposal,
    register_connection,
    unregister_connection,
)

logger = logging.getLogger(__name__)

router = APIRouter()

__all__ = ["router", "broadcast_proposal"]


@router.websocket("/evolution")
async def evolution_proposals_stream(ws: WebSocket) -> None:
    """WebSocket endpoint for receiving real-time Evolution Proposals."""
    if not await verify_ws_origin(ws):
        return
    await ws.accept()
    register_connection(ws)
    logger.info("WebSocket client connected for evolution proposals (user: default)")

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected from evolution proposals (user: default)")
    except Exception as exc:
        logger.error("WebSocket error for user default: %s", exc)
    finally:
        unregister_connection(ws)
