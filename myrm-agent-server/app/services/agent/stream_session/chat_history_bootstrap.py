"""Bootstrap chat history before agent-stream param conversion.

[INPUT]
- app.services.agent.params::AgentRequest (POS: chat_id, query, resume/regenerate flags)
- app.services.chat.chat_service::ChatService (POS: persist user message + load history)

[OUTPUT]
- persist_user_message: append user turn and commit it before any turn setup
- load_chat_history: load web chat history after setup gates complete
- persist_user_message_and_load_history: compatibility helper combining both steps

[POS]
Orchestrator helper isolating DB persist + history load from stream session lifecycle.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.services.agent.params import AgentRequest, _extract_text_from_query
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)


async def persist_user_message_and_load_history(
    request: AgentRequest,
    *,
    text_content: str,
) -> list[list[str | dict[str, object]]]:
    """Persist a new user message, then load chat history for the stream."""
    persisted_message_id = await persist_user_message(
        request,
        text_content=text_content,
    )
    return await load_chat_history(
        request,
        exclude_message_id=persisted_message_id,
    )


async def persist_user_message(
    request: AgentRequest,
    *,
    text_content: str,
) -> str | None:
    """Commit the user row before optional pre-reply work can run.

    The early buffered stream is allowed to perform a stale-context compact
    before building the agent.  That work can involve profile and model-window
    resolution, so the user row must be committed in its own transaction first;
    otherwise the API can show no user turn while the accepted stream is still
    doing setup.
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
    logger.info(
        "E1 user row committed chat_id=%s message_id=%s persisted_id=%s",
        request.chat_id,
        request.message_id,
        msg.id,
    )
    return msg.id


async def load_chat_history(
    request: AgentRequest,
    *,
    exclude_message_id: str | None = None,
) -> list[list[str | dict[str, object]]]:
    """Load canonical history after all pre-agent setup gates have run."""
    if not request.chat_id:
        return []
    return await ChatService.load_web_chat_history(
        request.chat_id,
        exclude_message_id=exclude_message_id,
        api_key=None,
    )


def stream_text_content(request: AgentRequest) -> str:
    """Extract user text for a non-resume stream request."""
    if request.resume_value is not None:
        return ""
    return _extract_text_from_query(request.query)
