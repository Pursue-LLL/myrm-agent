"""Bootstrap chat history before agent-stream param conversion.

[INPUT]
- app.services.agent.params::AgentRequest (POS: chat_id, query, resume/regenerate flags)
- app.services.chat.chat_service::ChatService (POS: persist user message + load history)

[OUTPUT]
- persist_user_message_and_load_history: append user turn and return web chat history

[POS]
Orchestrator helper isolating DB persist + history load from stream session lifecycle.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.agent.params import AgentRequest, _extract_text_from_query
from app.services.chat.chat_service import ChatService


async def persist_user_message_and_load_history(
    request: AgentRequest,
    *,
    text_content: str,
) -> list[list[str | dict[str, object]]]:
    """Persist a new user message when allowed, then load chat history for the stream."""
    if not request.chat_id:
        return []

    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        is_regenerate = request.sibling_group_id is not None
        if request.resume_value is None and not is_regenerate:
            if request.timestamp is not None:
                sent_at_utc = datetime.fromtimestamp(request.timestamp, tz=UTC)
            else:
                sent_at_utc = datetime.now(tz=UTC)

            sent_timezone = request.timezone or "UTC"
            extra_data_val = None
            if isinstance(request.query, list):
                extra_data_val = {"original_query": request.query}

            msg = await ChatService.ensure_chat_and_append_user_message(
                chat_id=request.chat_id,
                content=text_content,
                sent_at=sent_at_utc,
                sent_timezone=sent_timezone,
                message_id=request.message_id,
                action_mode=request.action_mode,
                agent_id=request.agent_id or "default",
                ephemeral_subagents=request.ephemeral_subagents,
                extra_data=extra_data_val,
                is_incognito=request.incognito_mode,
                active_moa_preset_id=request.active_moa_preset_id,
                persist_moa_preset=(
                    request.action_mode == "agent" and not request.incognito_mode
                ),
            )
            chat_history = await ChatService.load_web_chat_history(
                request.chat_id,
                exclude_message_id=msg.id,
                api_key=None,
            )
        else:
            chat_history = await ChatService.load_web_chat_history(request.chat_id, api_key=None)
        await db.commit()
        return chat_history


def stream_text_content(request: AgentRequest) -> str:
    """Extract user text for a non-resume stream request."""
    if request.resume_value is not None:
        return ""
    return _extract_text_from_query(request.query)
