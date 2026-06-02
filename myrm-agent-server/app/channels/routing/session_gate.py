"""Session-level message debounce and concurrency gate.

Groups rapid-fire messages from the same conversation into a single
merged InboundMessage before forwarding to Agent execution.

Two complementary mechanisms:
1. **Debounce Timer**: Accumulates messages within a configurable time
   window (default 300 ms). The timer resets on each new message.
2. **Active-Session Pending Queue**: When a session already has an Agent
   task in progress, new messages are held in a pending queue. After the
   task completes, pending messages are merged and re-dispatched.

[INPUT]
- channels.routing.router_keys::routing_session_key (POS: debounce grouping key format, consistent with Router ``state_key``)

[OUTPUT]
- Merged InboundMessage delivered via callback to Router

[POS]
Sits between Router's consume loop and the per-message handler.
Transparent to channel providers and AgentExecutor.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable

from app.channels.routing.router_keys import routing_session_key
from app.channels.types import (
    ContextEntry,
    InboundMessage,
    MediaAttachment,
)

logger = logging.getLogger(__name__)

OnReady = Callable[[InboundMessage], Awaitable[None]]

_DEFAULT_DEBOUNCE_MS = 300
_MAX_PENDING = 10


@dataclasses.dataclass(frozen=True, slots=True)
class SessionGateConfig:
    """Debounce and concurrency-control parameters."""

    debounce_window_ms: int = _DEFAULT_DEBOUNCE_MS
    max_pending_per_session: int = _MAX_PENDING


@dataclasses.dataclass(slots=True)
class _SessionState:
    """Per-session mutable state managed by SessionGate."""

    buffer: list[InboundMessage] = dataclasses.field(default_factory=list)
    pending: list[InboundMessage] = dataclasses.field(default_factory=list)
    timer: asyncio.TimerHandle | None = None
    active: bool = False


def gate_key(msg: InboundMessage) -> str:
    """Derive a lightweight session key for debounce grouping.

    Uses channel + peer identifier (chat_id for groups, sender_id for DMs).
    Format matches ``routing_session_key``; missing peer uses ``"unknown"``.
    This is intentionally simpler than SessionKey (no user_id / agent_id)
    because debounce happens before identity resolution.
    """
    peer = msg.chat_id if msg.is_group and msg.chat_id else msg.sender_id
    return routing_session_key(msg.channel, peer or "unknown")


def merge_messages(msgs: tuple[InboundMessage, ...]) -> InboundMessage:
    """Merge multiple InboundMessages from the same session into one.

    Guarantees:
    - ``content``: newline-joined (preserves user's segmentation intent)
    - ``media``: concatenated in arrival order
    - ``context_messages``: concatenated in arrival order
    - ``metadata``: from the *last* message (keeps final message_id for reaction)
    - ``thread_id``: first non-None value
    - Other fields (channel, sender_id, chat_id, is_group, mentioned): from first message
    """
    if len(msgs) == 1:
        return msgs[0]

    first = msgs[0]
    last = msgs[-1]

    content_parts: list[str] = []
    all_media: list[MediaAttachment] = []
    all_context: list[ContextEntry] = []
    thread_id: str | None = None
    mentioned = False

    for m in msgs:
        if m.content.strip():
            content_parts.append(m.content)
        all_media.extend(m.media)
        all_context.extend(m.context_messages)
        if thread_id is None and m.thread_id:
            thread_id = m.thread_id
        if m.mentioned:
            mentioned = True

    return InboundMessage(
        channel=first.channel,
        sender_id=first.sender_id,
        content="\n".join(content_parts),
        chat_id=first.chat_id,
        user_id=first.user_id,
        sender_name=first.sender_name,
        is_group=first.is_group,
        mentioned=mentioned,
        media=tuple(all_media),
        metadata=dict(last.metadata),
        reply_to_id=first.reply_to_id,
        thread_id=thread_id,
        context_messages=tuple(all_context),
        message_id=last.message_id,
        sent_at=first.sent_at,
        sent_timezone=first.sent_timezone,
    )


class SessionGate:
    """Debounce + concurrency gate for inbound messages.

    Usage::

        gate = SessionGate(config, on_ready=router._handle_merged)
        # In consume loop:
        gate.submit(msg)
        # After agent completes (``gate_key`` is derived from the message; same channel/peer as merged inbound):
        gate.on_task_complete(msg)
    """

    def __init__(self, config: SessionGateConfig, *, on_ready: OnReady) -> None:
        self._config = config
        self._on_ready = on_ready
        self._sessions: dict[str, _SessionState] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    def _get_state(self, key: str) -> _SessionState:
        state = self._sessions.get(key)
        if state is None:
            state = _SessionState()
            self._sessions[key] = state
        return state

    def submit(self, msg: InboundMessage) -> None:
        """Submit a message for debounce or pending accumulation."""
        key = gate_key(msg)
        state = self._get_state(key)

        if state.active:
            if len(state.pending) < self._config.max_pending_per_session:
                state.pending.append(msg)
            else:
                logger.warning(
                    "SessionGate: pending queue full for %s, dropping message",
                    key,
                )
            return

        window = self._config.debounce_window_ms
        if window <= 0:
            asyncio.ensure_future(self._fire(key, (msg,)))
            return

        state.buffer.append(msg)
        if state.timer is not None:
            state.timer.cancel()

        loop = self._ensure_loop()
        state.timer = loop.call_later(
            window / 1000.0,
            self._timer_fired,
            key,
        )

    def _timer_fired(self, key: str) -> None:
        """Called when debounce timer expires — flush buffer."""
        state = self._sessions.get(key)
        if not state or not state.buffer:
            return
        msgs = tuple(state.buffer)
        state.buffer.clear()
        state.timer = None
        state.active = True
        asyncio.ensure_future(self._fire(key, msgs))

    async def _fire(self, key: str, msgs: tuple[InboundMessage, ...]) -> None:
        """Merge messages and invoke the on_ready callback.

        After ``on_ready`` completes (success or failure), drains the pending
        queue. ``on_task_complete`` also calls ``_drain_pending``; the method
        is idempotent (no-op when ``state.active`` is already ``False``).
        """
        state = self._get_state(key)
        state.active = True
        merged = merge_messages(msgs)
        try:
            await self._on_ready(merged)
        except Exception:
            logger.warning("SessionGate: on_ready callback failed for %s", key, exc_info=True)
        finally:
            self._drain_pending(key)

    def _drain_pending(self, key: str) -> None:
        """After task completes, drain and re-dispatch pending messages.

        Idempotent: no-op if the session is not active (already drained).
        """
        state = self._sessions.get(key)
        if not state or not state.active:
            return
        state.active = False

        if not state.pending:
            if not state.buffer:
                self._sessions.pop(key, None)
            return

        pending = tuple(state.pending)
        state.pending.clear()
        asyncio.ensure_future(self._fire(key, pending))

    def on_task_complete(self, msg: InboundMessage) -> None:
        """Signal that the agent task for this session has completed.

        Called by Router in the finally block after agent execution.
        """
        key = gate_key(msg)
        self._drain_pending(key)

    def pending_count(self, key: str) -> int:
        """Return the number of pending messages queued for a session key."""
        state = self._sessions.get(key)
        return len(state.pending) if state else 0

    def clear(self) -> None:
        """Cancel all timers and clear state (called on Router.stop)."""
        for state in self._sessions.values():
            if state.timer is not None:
                state.timer.cancel()
        self._sessions.clear()
