"""WebSocket Batch Progress Streaming

Real-time progress updates for batch optimization tasks via WebSocket.

Protocol:
  1. Client opens WS to /ws/skill-optimization/batch/{batch_id}
  2. Server pushes progress updates in JSON format
  3. Client receives: {"type": "progress", "batch_id": "...", "data": {...}}
  4. Server auto-closes when batch completes or client disconnects
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.infra.ws_origin_guard import verify_ws_origin

logger = logging.getLogger(__name__)

router = APIRouter()

_WS_CLOSE_NORMAL = 1000
_WS_CLOSE_ERROR = 1011
_HEARTBEAT_INTERVAL = 30.0

_active_connections: dict[str, list[WebSocket]] = defaultdict(list)
_subscription_lock = asyncio.Lock()


@router.websocket("/batch/{batch_id}")
async def batch_progress_stream(batch_id: str, ws: WebSocket) -> None:
    """WebSocket endpoint for real-time batch progress updates

    Args:
        batch_id: Batch task identifier to subscribe to
        ws: WebSocket connection
    """
    if not await verify_ws_origin(ws):
        return
    await ws.accept()

    async with _subscription_lock:
        _active_connections[batch_id].append(ws)

    logger.info(f"Client subscribed to batch {batch_id} progress (total: {len(_active_connections[batch_id])})")

    try:
        await ws.send_json(
            {
                "type": "subscribed",
                "batch_id": batch_id,
                "message": "Successfully subscribed to batch progress updates",
            }
        )

        heartbeat_task = asyncio.create_task(_send_heartbeat(ws))

        while True:
            try:
                message = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
                data = json.loads(message)

                if data.get("action") == "ping":
                    await ws.send_json({"type": "pong"})
                elif data.get("action") == "unsubscribe":
                    break

            except asyncio.TimeoutError:
                continue
            except (json.JSONDecodeError, WebSocketDisconnect):
                break

    except Exception as e:
        logger.error(f"WebSocket error for batch {batch_id}: {e}")
    finally:
        heartbeat_task.cancel()
        async with _subscription_lock:
            if ws in _active_connections[batch_id]:
                _active_connections[batch_id].remove(ws)
            if not _active_connections[batch_id]:
                del _active_connections[batch_id]

        logger.info(f"Client unsubscribed from batch {batch_id} (remaining: {len(_active_connections.get(batch_id, []))})")

        try:
            await ws.close(code=_WS_CLOSE_NORMAL)
        except Exception:
            pass


async def _send_heartbeat(ws: WebSocket) -> None:
    """Send periodic heartbeat to keep connection alive

    Args:
        ws: WebSocket connection
    """
    try:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            await ws.send_json({"type": "heartbeat"})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass


async def broadcast_batch_progress(batch_id: str, progress_data: dict[str, Any]) -> None:
    """Broadcast batch progress to all subscribed clients

    Args:
        batch_id: Batch task identifier
        progress_data: Progress data to broadcast
    """
    async with _subscription_lock:
        connections = _active_connections.get(batch_id, [])
        if not connections:
            return

    message = {
        "type": "progress",
        "batch_id": batch_id,
        "data": progress_data,
    }

    disconnected = []
    for ws in connections:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send progress to client: {e}")
            disconnected.append(ws)

    if disconnected:
        async with _subscription_lock:
            for ws in disconnected:
                if ws in _active_connections[batch_id]:
                    _active_connections[batch_id].remove(ws)
            if not _active_connections[batch_id]:
                del _active_connections[batch_id]


async def broadcast_batch_completion(batch_id: str, final_data: dict[str, Any]) -> None:
    """Broadcast batch completion to all subscribed clients and close connections

    Args:
        batch_id: Batch task identifier
        final_data: Final batch data
    """
    async with _subscription_lock:
        connections = _active_connections.get(batch_id, [])
        if not connections:
            return

    message = {
        "type": "completed",
        "batch_id": batch_id,
        "data": final_data,
    }

    for ws in connections:
        try:
            await ws.send_json(message)
            await ws.close(code=_WS_CLOSE_NORMAL)
        except Exception as e:
            logger.warning(f"Failed to send completion to client: {e}")

    async with _subscription_lock:
        if batch_id in _active_connections:
            del _active_connections[batch_id]

    logger.info(f"Batch {batch_id} completed, closed {len(connections)} WebSocket connections")


def get_active_subscriptions() -> dict[str, int]:
    """Get active WebSocket subscriptions count per batch

    Returns:
        dict[str, int]: Mapping of batch_id to subscriber count
    """
    return {batch_id: len(connections) for batch_id, connections in _active_connections.items()}
