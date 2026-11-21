"""Which groups the channel budget panel can offer, and which of its channels have been seen.

[INPUT]
- app.database.models.chat::Chat (POS: Every channel conversation, stored under its session key)
- app.database.repositories.channel_key_match::channel_key_extends (POS: Boundary-safe match of a conversation's key and the keys that continue it)
- app.platform_utils::get_session_factory (POS: Async session factory)
- app.services.budget.channel_budget_key::GROUP_PEER_KIND, budget_key_of_session_key (POS: Canonical channel budget key)

[OUTPUT]
- list_known_group_keys: Budget keys of the groups that have a chat, most recently active first
- mark_known_groups: Channel statuses each with ``known``, whether a chat of that group is on record

[POS]
Read side of the budget panel's group picker. A group is known while a chat of it is on record, matched on the key's
segment boundary (``channel_key_extends``) as the cost recovery and the audit do (the guard looks up the exact budget
key of each live group message instead); the panel flags a policy whose key no chat extends, so a key typed by hand
can be checked.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select

from app.database.models.chat import Chat
from app.database.repositories.channel_key_match import channel_key_extends
from app.platform_utils import get_session_factory
from app.services.budget.channel_budget_key import GROUP_PEER_KIND, budget_key_of_session_key

logger = logging.getLogger(__name__)

# Narrows the scan to rows that mention a group; the exact peer kind is checked on the parsed key.
_GROUP_SESSION_KEY_LIKE = f"%:{GROUP_PEER_KIND}:%"


async def list_known_group_keys() -> list[str]:
    """Budget keys of every group that has a chat, the most recently active first.

    Chats of one group (a new epoch, a topic, an agent) collapse into one key whose activity is the latest of them.
    """
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Chat.channel_session_key, Chat.updated_at).where(Chat.channel_session_key.like(_GROUP_SESSION_KEY_LIKE))
        )
        rows = result.all()
    last_active: dict[str, datetime] = {}
    for session_key, updated_at in rows:
        key = budget_key_of_session_key(session_key)
        if key is not None and updated_at >= last_active.get(key, updated_at):
            last_active[key] = updated_at
    return sorted(last_active, key=lambda key: (last_active[key], key), reverse=True)


async def mark_known_groups(statuses: list[dict[str, object]]) -> list[dict[str, object]]:
    """``statuses`` each with ``known``: whether a chat of that channel's group is on record.

    A failed lookup marks every channel known, so a database hiccup never makes the panel doubt a correct key.
    """
    keys = [str(status["channel_key"]) for status in statuses]
    try:
        known = await _keys_with_a_chat(keys)
    except Exception:
        logger.warning("Could not tell which budgeted groups have a chat; treating them all as seen", exc_info=True)
        known = set(keys)
    return [{**status, "known": key in known} for status, key in zip(statuses, keys, strict=True)]


async def _keys_with_a_chat(keys: list[str]) -> set[str]:
    """The ``keys`` that a chat extends; one index probe per key that stops at the first chat, so the other chats of a
    group are never read."""
    async with get_session_factory()() as session:
        return {
            key
            for key in keys
            if await session.scalar(select(Chat.channel_session_key).where(channel_key_extends(key)).limit(1)) is not None
        }
