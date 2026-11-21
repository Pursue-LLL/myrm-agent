"""Canonical key of a group's channel budget.

[INPUT]
- app.channels.types.session::SessionKey (POS: Structured session identifier; every chat of a channel conversation is stored under its serialisation)

[OUTPUT]
- GROUP_PEER_KIND: The peer kind of a group inside a session key
- group_budget_key: Budget key of a group, built the way the session keys of its chats are
- budget_key_of_session_key: Budget key of the group a stored session key belongs to; None for any other conversation
- normalize_channel_budget_key: Canonical form of a stored or typed key; never raises
- parse_channel_budget_key: Canonical form of a typed key; rejects keys that are not of the form {channel}:group:{chat id}

[POS]
Single definition of the channel budget key. The chats of a group are stored under ``SessionKey.to_str()`` with an
epoch, topic or agent appended, so the budget key is that serialisation without the suffix. The runtime guard, the
restart cost recovery and the audit all match this one string, which is why every producer goes through here.
"""

from __future__ import annotations

import re

from app.channels.types import SessionKey

GROUP_PEER_KIND = "group"
_GROUP_KEY = re.compile(rf"[^:]+:{GROUP_PEER_KIND}:[^:]+")


def group_budget_key(channel: str, peer_id: str) -> str:
    """Budget key of the group ``peer_id`` on ``channel``: its session key without epoch, topic or agent."""
    return SessionKey(channel=channel, peer_kind=GROUP_PEER_KIND, peer_id=peer_id).to_str()


def budget_key_of_session_key(session_key: str | None) -> str | None:
    """Budget key of the group a stored session key belongs to.

    ``None`` for the key of any other conversation, for a chat without a channel key and for a group no policy could be
    stored under (the keys returned are the ones ``parse_channel_budget_key`` accepts unchanged).
    """
    parsed = SessionKey.parse(session_key) if session_key else None
    if parsed is None or parsed.peer_kind != GROUP_PEER_KIND:
        return None
    key = group_budget_key(parsed.channel, parsed.peer_id)
    return key if _GROUP_KEY.fullmatch(key) else None


def normalize_channel_budget_key(raw: str) -> str:
    """Canonical form of a stored or typed key: the channel and peer sanitised and the whole key lowercased.

    A key without the ``{channel}:{peer_kind}:{peer}`` shape cannot name a group, so it is only trimmed and lowercased;
    such rows stay listable and deletable.
    """
    key = raw.strip()
    parts = key.split(":", 2)
    if len(parts) < 3:
        return key.lower()
    return SessionKey(channel=parts[0], peer_kind=parts[1], peer_id=parts[2]).to_str()


def parse_channel_budget_key(raw: str) -> str:
    """Canonical key of a group typed by the user.

    Raises:
        ValueError: The key does not name a group, so no message could ever match the policy.
    """
    key = normalize_channel_budget_key(raw)
    if not _GROUP_KEY.fullmatch(key):
        raise ValueError("Channel budget key must have the form <channel>:group:<chat id>, for example telegram:group:chat_123")
    return key
