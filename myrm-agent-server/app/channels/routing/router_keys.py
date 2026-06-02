"""Stable string keys for routing maps (active tasks, approvals, session markers).

[OUTPUT]
- routing_session_key

[POS]
``routing_session_key`` builds ``f"{channel}:{peer_id}"`` for DM/group peer maps
(``peer_id`` is ``sender_id`` in DM, ``chat_id`` in groups when resolved).
Inbound dedup uses ``f"{channel}:{message_id}"`` in ``router.py``; that is a different key shape.
"""

from __future__ import annotations


def routing_session_key(channel: str, peer_id: str) -> str:
    """Return the map key ``f"{channel}:{peer_id}"`` used across router modules."""
    return f"{channel}:{peer_id}"
