"""Workspace SSE Multiplexer for multi-tab support."""

import asyncio
import logging
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


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

    async def publish(self, chat_id: str | None, message_id: str, chunk: str) -> None:
        """Publish a chunk to all multiplexed subscribers.

        The chunk is already an SSE formatted string (e.g., 'event: message\\ndata: {...}\\n\\n').
        We need to inject the chat_id and message_id so the frontend knows where to route it.
        Since we can't easily parse and rebuild the SSE string without overhead,
        we can wrap it in a custom multiplex event, OR we can just rely on the
        frontend to parse the payload. Wait, the payload already contains messageId!
        But does it contain chat_id?
        Actually, the easiest way is to wrap the raw chunk in a new SSE event:
        event: multiplex
        data: {"chat_id": "...", "message_id": "...", "raw_chunk": "..."}
        """
        import json

        if not self._subscribers:
            return

        payload = json.dumps({"chat_id": chat_id, "message_id": message_id, "raw_chunk": chunk})

        multiplexed_chunk = f"event: multiplex\ndata: {payload}\n\n"

        dead_queues = set()
        for queue in self._subscribers:
            try:
                queue.put_nowait(multiplexed_chunk)
            except asyncio.QueueFull:
                dead_queues.add(queue)

        for q in dead_queues:
            self._subscribers.discard(q)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribe to the multiplexed stream."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)

        try:
            while True:
                chunk = await queue.get()
                yield chunk
        except asyncio.CancelledError:
            pass
        finally:
            self._subscribers.discard(queue)
