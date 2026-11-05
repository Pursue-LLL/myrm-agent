"""[INPUT]
- app.database.repositories.conversation_recall (POS: prior-chat summary/snippet recall index)
- app.services.chat.chat_crud (POS: chat metadata)
- ..context::MentionContext (POS: per-turn accumulation state)
- ..xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- _MENTION_PRIOR_CHAT_FALLBACK_WORKSPACE: workspace stand-in for @chat: (prior-chat reads no files)
- _load_prior_chat_document / _prior_chat_part: recall document load + fragment rendering
- prior_chat_part: @chat: handler

[POS]
Prior-conversation @ references. Incognito web chats are refused, imported transcripts are allowed
(their flag only keeps them out of the sidebar), and a missing recall row is rebuilt once.
"""

from __future__ import annotations

import logging

from ...models import MentionReferenceRequest
from ..context import MentionContext
from ..xml import _can_inline, _format_size, _xml_error, _xml_metadata, _xml_part

logger = logging.getLogger(__name__)

_MENTION_PRIOR_CHAT_FALLBACK_WORKSPACE = "/tmp"


async def _load_prior_chat_document(chat_id: str):
    from app.database.repositories.conversation_recall.lookup_repo import (
        ConversationRecallLookupRepository,
    )
    from app.database.repositories.uow import UnitOfWork

    async with UnitOfWork() as uow:
        session = uow.session
        if session is None:
            return None
        return await ConversationRecallLookupRepository.fetch_prior_chat_document(
            session,
            chat_id=chat_id,
        )


async def _prior_chat_part(
    chat_id: str,
    display: str,
    current_total_bytes: int,
) -> tuple[str, int]:
    """Resolve a prior chat mention into summary + snippet context."""
    from myrm_agent_harness.toolkits.memory.conversation_search.types import (
        MAX_SNIPPET_CHARS,
        MAX_SUMMARY_CHARS,
    )

    from app.database.repositories.uow import UnitOfWork
    from app.services.chat.chat_crud import _ChatCrudMixin
    from app.services.chat.conversation_recall_index_service import (
        ConversationRecallIndexService,
    )

    chat = await _ChatCrudMixin.get_chat_metadata(chat_id)
    if chat is None:
        return _xml_error(display, "chat not found"), 0
    # Imported external transcripts carry the incognito flag only to stay out of the sidebar; they are real history.
    if chat.is_incognito and chat.source == "web":
        return _xml_error(display, "incognito chats cannot be referenced"), 0

    row = await _load_prior_chat_document(chat_id)
    if row is None:
        async with UnitOfWork() as uow:
            session = uow.session
            if session is not None:
                await ConversationRecallIndexService.rebuild_chat(session, chat_id)
        row = await _load_prior_chat_document(chat_id)

    if row is None:
        return _xml_error(display, "recall index unavailable"), 0
    if row.is_excluded:
        return _xml_error(display, "chat is excluded from recall"), 0

    title = row.title or chat.title or "Untitled conversation"
    summary = row.summary[:MAX_SUMMARY_CHARS]
    snippet = row.snippet[:MAX_SNIPPET_CHARS]
    body_parts = [f"conversation_id: {chat_id}", f"title: {title}"]
    if summary:
        body_parts.append(f"summary: {summary}")
    if snippet:
        body_parts.append(f"snippet: {snippet}")
    content = "\n".join(body_parts)
    content_bytes = len(content.encode("utf-8"))
    if _can_inline(content_bytes, current_total_bytes):
        return _xml_part(display, "prior-chat", content), content_bytes
    return (
        _xml_metadata(display, "prior-chat", f"Context too large ({_format_size(content_bytes)})"),
        0,
    )


async def prior_chat_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    chat_id = ref.path or ref.file_id or ""
    display = ref.label or f"@chat:{chat_id}"
    if not chat_id:
        ctx.parts.append(_xml_error(display, "missing chat_id"))
        return
    part, consumed_bytes = await _prior_chat_part(chat_id, display, ctx.total_bytes)
    ctx.parts.append(part)
    ctx.total_bytes += consumed_bytes
