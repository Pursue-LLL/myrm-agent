"""Router session mixin: /new, /compact, /retry, /undo, topic commands.

[INPUT]
- channels.routing.commands::handle_new_session, handle_compact, handle_retry, handle_undo, handle_topic_command (POS: slash command handlers.)
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.routing.router_keys::routing_session_key (POS: channel+peer mapping key format.)
- channels.types::InboundMessage (POS: channel message types.)

[OUTPUT]
- RouterCommandsSessionMixin: session boundary and turn-management slash handlers

[POS]
Router session mixin segment. Handles /new cleanup chain, context compact,
retry/undo delegation, and topic bind/unbind commands.
"""

from __future__ import annotations

import logging

from app.channels.i18n import get_text
from app.channels.routing.commands import (
    TopicCommand,
    handle_compact,
    handle_new_session,
    handle_retry,
    handle_topic_command,
    handle_undo,
)
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.routing.router_keys import routing_session_key
from app.channels.types import InboundMessage

logger = logging.getLogger("app.channels.routing.router")

class RouterCommandsSessionMixin:
    """Mixin: /new, /compact, /retry, /undo, and topic commands."""

    async def _handle_new_session(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Handle /new command: cancel running task, flush pending queue, start fresh."""
        chat_id = msg.chat_id or msg.sender_id
        state_key = routing_session_key(msg.channel, chat_id)

        await self._abort_session_task(
            state_key,
            reason="User /new command",
            placeholder_text=get_text(msg, "placeholder_stopped"),
        )
        dropped = self._gate.clear_pending_for_key(state_key)
        if dropped:
            logger.info(
                "AgentRouter: /new dropped %d pending message(s) for %s",
                dropped,
                state_key,
            )

        self._session_yolo.pop(state_key, None)
        self._session_personality.pop(state_key, None)

        await handle_new_session(msg, self._bus, self._new_session_peers)

    async def _handle_compact(self: RouterCommandsHost, msg: InboundMessage, raw_args: str = "") -> None:
        """Handle /compact command: compress chat context to reduce token cost."""
        await handle_compact(
            msg,
            self._bus,
            self._resolver,
            self._compact_handler,
            focus_topic=raw_args.strip(),
        )

    async def _handle_retry(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Handle /retry command: delete last assistant turn and re-execute with original query."""
        retried_msg = await handle_retry(msg, self._bus, self._resolver, self._retry_handler)
        if retried_msg is not None:
            self._gate.submit(retried_msg)

    async def _handle_undo(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Handle /undo command: delete the entire last turn."""
        await handle_undo(msg, self._bus, self._resolver, self._undo_handler)

    async def _handle_topic_command(self: RouterCommandsHost, msg: InboundMessage, cmd: TopicCommand) -> None:
        """Handle /bind, /unbind, /topic commands for topic management."""
        await handle_topic_command(msg, cmd, self._bus, self._topic_resolver)
