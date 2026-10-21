"""UI Request Manager for Bi-Directional Client Interaction Handshake.

[INPUT]
- UIRequest, UIResponse from myrm_agent_harness.agent.ui
- ReversePushUIContext from myrm_agent_harness.agent.ui

[OUTPUT]
- UIRequestManager, get_ui_request_manager()

[POS]
Server-side coordination service managing pending Extension UI requests per chat session (Item 28).
Provides thread-safe registration, resolution, and cancellation of interactive user frames.
File length < 220 lines. Zero `Any`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from myrm_agent_harness.agent.ui import ReversePushUIContext, UIRequest, UIResponse

logger = logging.getLogger(__name__)


class UIRequestManager:
    """Manages active UI requests awaiting client response across chat sessions."""

    def __init__(self) -> None:
        # chat_id -> dict of request_id -> (UIRequest, ReversePushUIContext)
        self._pending_by_chat: dict[str, dict[str, tuple[UIRequest, ReversePushUIContext]]] = {}
        # active context per chat: chat_id -> ReversePushUIContext
        self._contexts_by_chat: dict[str, ReversePushUIContext] = {}
        self._lock = asyncio.Lock()

    async def register_context(self, chat_id: str, context: ReversePushUIContext) -> None:
        """Associates a ReversePushUIContext with a chat session."""
        async with self._lock:
            self._contexts_by_chat[chat_id] = context
            if chat_id not in self._pending_by_chat:
                self._pending_by_chat[chat_id] = {}
            logger.info("[UIRequestManager] Registered ReversePushUIContext for chat %s", chat_id)

    async def unregister_context(self, chat_id: str) -> None:
        """Removes the associated context when chat run finishes."""
        async with self._lock:
            self._contexts_by_chat.pop(chat_id, None)
            self._pending_by_chat.pop(chat_id, None)
            logger.info("[UIRequestManager] Unregistered ReversePushUIContext for chat %s", chat_id)

    def get_context(self, chat_id: str) -> ReversePushUIContext | None:
        """Gets active context for a chat session."""
        return self._contexts_by_chat.get(chat_id)

    async def record_request(self, chat_id: str, request: UIRequest, context: ReversePushUIContext) -> None:
        """Records an outgoing UIRequest pending user response."""
        async with self._lock:
            if chat_id not in self._pending_by_chat:
                self._pending_by_chat[chat_id] = {}
            self._pending_by_chat[chat_id][request.request_id] = (request, context)
            logger.info(
                "[UIRequestManager] Recorded pending %s request %s for chat %s",
                request.request_type,
                request.request_id,
                chat_id,
            )

    async def get_pending_requests(self, chat_id: str) -> Sequence[UIRequest]:
        """Returns all pending requests for a given chat session."""
        async with self._lock:
            chat_pending = self._pending_by_chat.get(chat_id, {})
            # Filter out already resolved requests
            active_requests: list[UIRequest] = []
            for req_id, (req, ctx) in list(chat_pending.items()):
                if ctx.is_pending(req_id):
                    active_requests.append(req)
                else:
                    # Clean up resolved entry
                    chat_pending.pop(req_id, None)
            return tuple(active_requests)

    async def resolve_response(self, chat_id: str, response: UIResponse) -> bool:
        """Resolves a pending UI request with an incoming client UIResponse frame."""
        async with self._lock:
            chat_pending = self._pending_by_chat.get(chat_id)
            if not chat_pending or response.request_id not in chat_pending:
                logger.warning(
                    "[UIRequestManager] No pending request found for %s in chat %s",
                    response.request_id,
                    chat_id,
                )
                return False

            _, context = chat_pending.pop(response.request_id)

        # Resolve future on the context
        return await context.resolve_response(response)

    async def cancel_request(
        self,
        chat_id: str,
        request_id: str,
        reason: str = "Interaction cancelled by operator",
    ) -> bool:
        """Cancels a pending request in the given chat session."""
        async with self._lock:
            chat_pending = self._pending_by_chat.get(chat_id)
            if not chat_pending or request_id not in chat_pending:
                return False

            _, context = chat_pending.pop(request_id)

        return await context.cancel_request(request_id, reason=reason)


_GLOBAL_UI_REQUEST_MANAGER: UIRequestManager | None = None


def get_ui_request_manager() -> UIRequestManager:
    """Returns singleton instance of UIRequestManager."""
    global _GLOBAL_UI_REQUEST_MANAGER
    if _GLOBAL_UI_REQUEST_MANAGER is None:
        _GLOBAL_UI_REQUEST_MANAGER = UIRequestManager()
    return _GLOBAL_UI_REQUEST_MANAGER
