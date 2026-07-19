"""Resolve wiki vault scope from chat or explicit agent identifiers.

[INPUT]
- app.services.chat.chat_service (POS: chat metadata lookup)

[OUTPUT]
- resolve_chat_agent_id(): agent_id bound to a chat session

[POS]
Wiki agent scope resolver. Maps chat_id to agent_id for agent-scoped vault paths.
"""

from __future__ import annotations

from app.services.chat.chat_service import ChatService


async def resolve_chat_agent_id(chat_id: str | None) -> str | None:
    """Return the agent_id bound to a chat, if any."""
    if not chat_id:
        return None
    chat = await ChatService.get_chat_metadata(chat_id)
    return chat.agent_id if chat else None
