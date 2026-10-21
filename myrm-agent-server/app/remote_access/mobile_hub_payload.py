"""Payload assembly for the Mobile Hub sessions endpoint.

Keeps the hub response self-sufficient: active cards carry agent display
names, and finished chats are listed alongside so the phone keeps an entry
point to task results after a session completes.

[POS]
Mobile Hub payload assembly layer. Composes agent display names, active
session cards, and finished chat listings into the hub response.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.gateway import AgentGateway


async def resolve_agent_display_names() -> dict[str, str]:
    """Map agent IDs to display names for hub cards (one query per request)."""
    from app.services.agent.agent_service import AgentService

    agents_raw, _ = await AgentService.get_agent_list(page=1, page_size=100)
    return {str(agent.id): agent.display_name or str(agent.id) for agent in agents_raw}


def annotate_active_sessions(
    gateway: AgentGateway,
    agent_names: dict[str, str],
) -> tuple[list[dict[str, object]], set[str]]:
    """Attach agentName to each active session card; return (cards, active chat IDs)."""
    active_sessions = gateway.get_active_sessions()
    active_chat_ids: set[str] = set()
    for session in active_sessions:
        chat_id = session.get("chatId")
        if isinstance(chat_id, str):
            active_chat_ids.add(chat_id)
        agent_id = session.get("agentId")
        if isinstance(agent_id, str):
            session["agentName"] = agent_names.get(agent_id)
    return active_sessions, active_chat_ids


async def build_recent_sessions(
    active_chat_ids: set[str],
    agent_names: dict[str, str],
    limit: int = 10,
) -> list[dict[str, object]]:
    """Recently updated chats for the finished-tasks section.

    ``get_chat_list`` already excludes trashed and incognito chats; chats that
    are currently active are skipped so no card appears in both sections.
    """
    from app.services.chat.chat_service import ChatService

    chats, _total = await ChatService.get_chat_list(page=1, page_size=limit)
    recent: list[dict[str, object]] = []
    for chat in chats:
        if chat.id in active_chat_ids:
            continue
        agent_id = chat.agent_id or ""
        recent.append(
            {
                "chatId": chat.id,
                "title": chat.title,
                "agentId": chat.agent_id,
                "agentName": agent_names.get(agent_id),
                "updatedAt": chat.updated_at.isoformat(),
            }
        )
    return recent
