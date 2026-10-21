"""Bootstrap chat history before agent-stream param conversion.

[INPUT]
- app.services.agent.params::AgentRequest (POS: chat_id, query, resume/regenerate flags)
- app.services.chat.chat_service::ChatService (POS: persist user message + load history)

[OUTPUT]
- persist_user_message: append user turn and commit it before any turn setup
- load_chat_history: load web chat history after setup gates complete (a regenerate's own query is not history)

[POS]
Orchestrator helper isolating DB persist + history load from stream session lifecycle.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.services.agent.params import AgentRequest, _extract_text_from_query
from app.services.agent.stream_session.lazy_session_gate import PendingSessionDraft
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)


class BootstrappedMessageId(str):
    """String message ID with attached pending lazy session draft when deferred."""

    pending_draft: PendingSessionDraft | None = None

    def __new__(
        cls,
        value: str,
        pending_draft: PendingSessionDraft | None = None,
    ) -> BootstrappedMessageId:
        instance = super().__new__(cls, value)
        instance.pending_draft = pending_draft
        return instance


async def persist_user_message(
    request: AgentRequest,
    *,
    text_content: str,
) -> BootstrappedMessageId | None:
    """Commit the user row for existing chats, or defer persistence for new chats.

    For new sessions, database persistence is deferred until the first active
    assistant output (First Token Barrier), preventing ghost empty sessions.
    """
    if not request.chat_id:
        logger.info("E1 user persist skipped: missing chat_id message_id=%s", request.message_id)
        return None

    is_regenerate = request.sibling_group_id is not None
    if request.resume_value is not None or is_regenerate:
        logger.info(
            "E1 user persist skipped: resume_or_regenerate chat_id=%s message_id=%s resume=%s regenerate=%s",
            request.chat_id,
            request.message_id,
            request.resume_value is not None,
            is_regenerate,
        )
        return None

    if request.timestamp is not None:
        sent_at_utc = datetime.fromtimestamp(request.timestamp, tz=UTC)
    else:
        sent_at_utc = datetime.now(tz=UTC)

    sent_timezone = request.timezone or "UTC"
    extra_data_val: dict[str, object] | None = None
    if isinstance(request.query, list):
        extra_data_val = {"original_query": request.query}

    existing_chat = await ChatService.get_chat_metadata(request.chat_id)
    if existing_chat is not None:
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
            persist_moa_preset=(request.action_mode == "agent" and not request.incognito_mode),
            mark_read=True,
        )
        logger.info(
            "E1 user row committed for existing chat_id=%s message_id=%s persisted_id=%s",
            request.chat_id,
            request.message_id,
            msg.id,
        )
        return BootstrappedMessageId(msg.id, pending_draft=None)

    # Defer persistence for new session until first assistant event
    resolved_id = request.message_id or str(uuid4())
    draft = PendingSessionDraft(
        chat_id=request.chat_id,
        user_content=text_content,
        sent_at=sent_at_utc,
        sent_timezone=sent_timezone,
        message_id=resolved_id,
        action_mode=request.action_mode,
        agent_id=request.agent_id or "default",
        ephemeral_subagents=request.ephemeral_subagents,
        extra_data=extra_data_val,
        is_incognito=request.incognito_mode,
        active_moa_preset_id=request.active_moa_preset_id,
        persist_moa_preset=(request.action_mode == "agent" and not request.incognito_mode),
    )
    logger.info(
        "E1 user persistence deferred for new chat_id=%s message_id=%s",
        request.chat_id,
        resolved_id,
    )
    return BootstrappedMessageId(resolved_id, pending_draft=draft)


async def load_chat_history(
    request: AgentRequest,
    *,
    exclude_message_id: str | None = None,
) -> list[list[str | dict[str, object]]]:
    """Load canonical history after all pre-agent setup gates have run.

    A regenerate persists no user row, so nothing can be excluded by id; the query it re-sends is the last user
    message of the chat, which would otherwise reach the model twice (once as history, once as the query).
    """
    if not request.chat_id:
        return []
    history = await ChatService.load_web_chat_history(
        request.chat_id,
        exclude_message_id=exclude_message_id,
        api_key=None,
    )
    if request.sibling_group_id is not None:
        for index in range(len(history) - 1, -1, -1):
            if history[index][0] == "human":
                del history[index]
                break
    return history


def stream_text_content(request: AgentRequest) -> str:
    """Extract user text for a non-resume stream request."""
    if request.resume_value is not None:
        return ""
    return _extract_text_from_query(request.query)
