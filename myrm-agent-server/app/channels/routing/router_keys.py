"""Stable string keys for routing maps (active tasks, approvals, session markers).

[INPUT]
- (none) Pure string builders; no imports.

[OUTPUT]
- routing_state_key: router state-map key carrying channel, peer and forum topic
- routing_session_key: chat-wide key for cross-topic chat lookups
- routing_enclave_key / parse_enclave_key: 4-tuple enclave form and its inverse

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


def routing_enclave_key(
    channel: str,
    peer_id: str,
    *,
    tenant_id: str = "default",
    agent_profile_id: str = "default",
) -> str:
    """Return the 4-tuple enclave isolation key ``tenant_id:channel:peer_id:agent_profile_id``.

    Ensures zero cross-talk between tenants, channels, senders, and different Agent profiles.
    """
    clean_tenant = (tenant_id or "default").strip() or "default"
    clean_channel = (channel or "unknown").strip() or "unknown"
    clean_peer = (peer_id or "anonymous").strip() or "anonymous"
    clean_agent = (agent_profile_id or "default").strip() or "default"
    return f"{clean_tenant}:{clean_channel}:{clean_peer}:{clean_agent}"


def parse_enclave_key(enclave_key: str) -> dict[str, str]:
    """Parse a 4-tuple enclave key back into its constituent components."""
    parts = enclave_key.split(":")
    if len(parts) >= 4:
        return {
            "tenant_id": parts[0],
            "channel": parts[1],
            "peer_id": ":".join(parts[2:-1]),
            "agent_profile_id": parts[-1],
        }
    if len(parts) == 2:
        return {
            "tenant_id": "default",
            "channel": parts[0],
            "peer_id": parts[1],
            "agent_profile_id": "default",
        }
    return {
        "tenant_id": "default",
        "channel": "unknown",
        "peer_id": enclave_key,
        "agent_profile_id": "default",
    }


__all__ = [
    "routing_enclave_key",
    "routing_session_key",
    "routing_state_key",
    "parse_enclave_key",
]
