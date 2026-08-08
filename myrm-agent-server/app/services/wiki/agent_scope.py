"""Resolve wiki vault scope from chat or explicit agent identifiers.

[INPUT]
- app.services.chat.chat_service (POS: chat metadata lookup)

[OUTPUT]
- resolve_chat_agent_id(): agent_id bound to a chat session
- normalize_agent_scope(): normalize agent_id to a UserConfig scope key

[POS]
Wiki agent scope utilities. Chat→agent resolution for vault paths and
agent_id→UserConfig scope normalization shared across wiki state stores.
"""

from __future__ import annotations

from app.services.chat.chat_service import ChatService

DEFAULT_AGENT_SCOPE = "__default__"


def normalize_agent_scope(agent_id: str | None) -> str:
    """Normalize an optional agent_id to a stable UserConfig scope key."""
    trimmed = (agent_id or "").strip()
    return trimmed or DEFAULT_AGENT_SCOPE


async def resolve_chat_agent_id(chat_id: str | None) -> str | None:
    """Return the agent_id bound to a chat, if any."""
    if not chat_id:
        return None
    chat = await ChatService.get_chat_metadata(chat_id)
    return chat.agent_id if chat else None
