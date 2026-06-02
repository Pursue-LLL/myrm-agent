"""Evolution proposal WebSocket hub — connection pool and broadcast (service layer)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

_active_connections: dict[str, list[WebSocket]] = defaultdict(list)


def get_active_connection_count(user_key: str = "default") -> int:
    """Return count of active evolution WS connections for monitoring."""
    return len(_active_connections.get(user_key, []))


async def broadcast_proposal(proposal_data: dict[str, Any], user_key: str = "default") -> None:
    """Broadcast an EvolutionProposal to all connected clients."""
    await broadcast_message("NEW_EVOLUTION_PROPOSAL", proposal_data, user_key=user_key)


async def broadcast_message(
    message_type: str,
    data: dict[str, object],
    user_key: str = "default",
) -> None:
    """Broadcast a typed JSON message to all evolution WebSocket clients."""
    connections = _active_connections.get(user_key, [])
    if not connections:
        logger.debug("No active WebSocket connections for user %s to receive proposal", user_key)
        return

    dead_connections: list[WebSocket] = []
    message = json.dumps({"type": message_type, "data": data})

    for ws in connections:
        try:
            await ws.send_text(message)
        except (WebSocketDisconnect, RuntimeError):
            dead_connections.append(ws)
        except Exception as exc:
            logger.error("Error sending proposal to WebSocket for user %s: %s", user_key, exc)
            dead_connections.append(ws)

    for ws in dead_connections:
        if ws in _active_connections[user_key]:
            _active_connections[user_key].remove(ws)

    if dead_connections:
        logger.info("Cleaned up %d dead connections for user %s", len(dead_connections), user_key)


def register_connection(ws: WebSocket, user_key: str = "default") -> None:
    """Register a WebSocket connection for evolution proposals."""
    _active_connections[user_key].append(ws)


def unregister_connection(ws: WebSocket, user_key: str = "default") -> None:
    """Remove a WebSocket connection from the pool."""
    if ws in _active_connections[user_key]:
        _active_connections[user_key].remove(ws)
