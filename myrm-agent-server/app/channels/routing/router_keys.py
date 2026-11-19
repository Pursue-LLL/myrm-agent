"""Stable string keys for routing maps (active tasks, approvals, session markers).

[INPUT]
- (none) Pure string builders; no imports.

[OUTPUT]
- routing_state_key: router state-map key carrying channel, peer and forum topic
- routing_session_key: chat-wide key for cross-topic chat lookups

[POS]
``routing_state_key`` builds the key for the router's in-memory state maps. It carries every
dimension those maps must separate: a Telegram supergroup topic can bind its own agent, so a
key without the topic would let two topics of one group overwrite each other's running task,
``/stop`` target, YOLO flag, pending approval and debounce queue.

It deliberately does not carry an agent id: a topic binds exactly one agent
(``SqlTopicManager`` keys bindings by ``(chat_id, thread_id)``), so the topic already
determines the agent and a second dimension would only fragment existing state.

Conversation history is keyed separately by ``app.channels.types.session.SessionKey``, which
encodes channel, peer, thread and agent for the ``Chat.channel_session_key`` column. The two
keys answer different questions and must not be substituted for one another.
"""

from __future__ import annotations

# Marks the chat-wide (no topic) scope, matching SqlTopicManager's storage key for a binding
# that applies to the whole group or DM.
_CHAT_SCOPE = "__chat__"


def routing_state_key(channel: str, peer_id: str, thread_id: str | None = None) -> str:
    """Return the router state-map key for one conversation scope.

    ``f"{channel}:{peer_id}"`` for DMs and untopiced chats, which is the format those
    conversations already use,
    ``f"{channel}:{peer_id}:{thread}"`` for a forum topic.
    """
    base = f"{channel}:{peer_id}"
    thread = (thread_id or "").strip()
    if not thread:
        return base
    return f"{base}:{thread}"


def routing_session_key(channel: str, peer_id: str) -> str:
    """Return the chat-scoped key ``f"{channel}:{peer_id}"``.

    Retained for the call sites that resolve a chat row across the whole chat rather than one
    topic's state; new state-map keys must use ``routing_state_key``.
    """
    return f"{channel}:{peer_id}"


__all__ = [
    "routing_session_key",
    "routing_state_key",
]
