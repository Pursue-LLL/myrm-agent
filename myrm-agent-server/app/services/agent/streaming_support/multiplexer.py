"""Workspace SSE Multiplexer for multi-tab support."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

# When agent-stream publishes before any /workspace/stream subscriber exists, chunks are
# buffered briefly so late-connecting browsers still receive tool_approval_request, etc.
_ORPHAN_BUFFER_MAX = 500


class WorkspaceMultiplexer:
    """A global event bus for multiplexing SSE streams across the workspace.

    This allows a single frontend connection to receive events for all active
    agent sessions, bypassing the browser's 6-connection limit.
    """

    _instance: "WorkspaceMultiplexer | None" = None

    @classmethod
    def get(cls) -> "WorkspaceMultiplexer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._orphan_buffer: list[str] = []

    def _broadcast(self, sse_chunk: str) -> None:
        """Broadcast a pre-formatted SSE chunk to all subscribers (fire-and-forget)."""
        if not self._subscribers:
            return
        dead_queues: set[asyncio.Queue[str]] = set()
        for queue in self._subscribers:
            try:
                queue.put_nowait(sse_chunk)
            except asyncio.QueueFull:
                dead_queues.add(queue)
        for q in dead_queues:
            self._subscribers.discard(q)

    def _buffer_orphan(self, sse_chunk: str) -> None:
        self._orphan_buffer.append(sse_chunk)
        if len(self._orphan_buffer) > _ORPHAN_BUFFER_MAX:
            self._orphan_buffer = self._orphan_buffer[-(_ORPHAN_BUFFER_MAX // 2) :]

    async def publish(self, chat_id: str | None, message_id: str, chunk: str) -> None:
        """Publish a raw SSE chunk wrapped in a multiplex envelope."""
        payload = json.dumps({"chat_id": chat_id, "message_id": message_id, "raw_chunk": chunk})
        envelope = f"event: multiplex\ndata: {payload}\n\n"
        if not self._subscribers:
            self._buffer_orphan(envelope)
            return
        self._broadcast(envelope)

    def publish_session_status(self, chat_id: str, status: str, agent_type: str = "") -> None:
        """Publish a session status change event (generating / awaiting_approval / idle)."""
        payload = json.dumps({"chat_id": chat_id, "status": status, "agent_type": agent_type})
        envelope = f"event: session_status\ndata: {payload}\n\n"
        if not self._subscribers:
            self._buffer_orphan(envelope)
            return
        self._broadcast(envelope)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribe to the multiplexed stream."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)

        for buffered in self._orphan_buffer:
            try:
                queue.put_nowait(buffered)
            except asyncio.QueueFull:
                logger.warning("WorkspaceMultiplexer orphan replay truncated for new subscriber")
                break

        try:
            while True:
                chunk = await queue.get()
                yield chunk
        except asyncio.CancelledError:
            pass
        finally:
            self._subscribers.discard(queue)
