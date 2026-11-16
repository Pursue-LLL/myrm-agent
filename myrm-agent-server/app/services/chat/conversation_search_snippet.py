"""Model-facing snippets of conversation search hits, read from redacted text.

[INPUT]
myrm_agent_harness.api::redact_sensitive_text (POS: credential masking SSOT)
myrm_agent_harness.toolkits.memory.conversation_search.types::ConversationSearchHit (POS: conversation search DTOs)
app.database.repositories.conversation_recall::ConversationRecallLookupRepository, WindowContext (POS: Conversation Recall 可见性查找仓储)
app.database.repositories.uow::UnitOfWork (POS: 全局工作单元模式)
app.services.chat.chat_helpers::strip_reasoning_tags (POS: removes reasoning tags from a text)

[OUTPUT]
redact_hit_windows: Give each hit the snippet window FTS5 chose, read from redacted text.
redacted_window: One window of a text as it reads once the whole text is redacted.

[POS]
会话召回片段脱敏层。FTS5 从存储原文里切窗口，凭据可能被切成任何脱敏规则都认不出的残片；本模块在整段已脱敏的原文上重建模型可见的窗口。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.api import redact_sensitive_text
from myrm_agent_harness.toolkits.memory.conversation_search.types import ConversationSearchHit
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall import ConversationRecallLookupRepository, WindowContext
from app.database.repositories.uow import UnitOfWork
from app.services.chat.chat_helpers import strip_reasoning_tags

logger = logging.getLogger(__name__)

# Stored text read on each side of a window. A credential beside the window is masked only when the redactor sees it
# whole, and a PEM private key runs to about 6.5k chars (RSA-8192).
_CONTEXT_CHARS = 8_000
# What FTS5 puts where its window does not reach the start or the end of the indexed text.
_ELLIPSIS = "..."


async def redact_hit_windows(hits: list[ConversationSearchHit]) -> list[ConversationSearchHit]:
    """Give each hit the window FTS5 chose, read from the redacted stored text as plain text.

    A hit whose window cannot be placed in the stored text, or lies inside a masked span, gets an empty snippet: an
    unredacted cut of the text is never handed on.
    """
    if not any(hit.snippet for hit in hits):
        return hits
    async with UnitOfWork() as uow:
        session = uow.session
        snippets = [await _rebuilt_snippet(session, hit) if session is not None else "" for hit in hits]
    return [hit.model_copy(update={"snippet": snippet}) for hit, snippet in zip(hits, snippets, strict=True)]


def redacted_window(text: str, start: int, end: int) -> str | None:
    """``text[start:end]`` as it reads once the whole text is redacted, or None if nothing of it can be shown.

    Redacting the window alone would miss a credential that continues past its edge, so the whole text is redacted and
    the window is read from the result. A mask replaces text of another length, so the result is lined up with the
    window from both ends: the text before the window and the text after it are each redacted alone, and the window is
    what lies between them. An edge inside a masked span does not line up; that side is then placed from the other
    edge and the raw window length, so the result takes in a little more text when masks shortened the window. When
    neither edge lines up, the window lies inside a masked span.
    """
    redacted = redact_sensitive_text(text)
    if redacted == text:
        return text[start:end]
    before = redact_sensitive_text(text[:start])
    after = redact_sensitive_text(text[end:])
    left = len(before) if redacted.startswith(before) else None
    right = len(redacted) - len(after) if redacted.endswith(after) else None
    width = end - start
    if left is None:
        if right is None:
            return None
        left = max(0, right - width)
    elif right is None:
        right = min(len(redacted), left + width)
    window = redacted[left:right]
    return window if window.strip() else None


async def _rebuilt_snippet(session: AsyncSession, hit: ConversationSearchHit) -> str:
    snippet = hit.snippet
    leading = snippet.startswith(_ELLIPSIS)
    trailing = len(snippet) > len(_ELLIPSIS) and snippet.endswith(_ELLIPSIS)
    window = snippet[len(_ELLIPSIS) if leading else 0 : len(snippet) - len(_ELLIPSIS) if trailing else len(snippet)]
    if not window.strip():
        return ""
    context = (
        _context_in(hit.summary, window)
        or _context_in(hit.title, window)
        or await ConversationRecallLookupRepository.fetch_window_context(
            session,
            chat_id=hit.conversation_id,
            message_id=hit.message_id,
            window=window,
            radius=_CONTEXT_CHARS,
        )
    )
    if context is None:
        logger.warning("Conversation snippet window not found in stored text; snippet dropped (chat_id=%s)", hit.conversation_id)
        return ""
    body = redacted_window(context.text, context.offset, context.offset + len(window))
    if body is None:
        return ""
    return strip_reasoning_tags(f"{_ELLIPSIS if leading else ''}{body}{_ELLIPSIS if trailing else ''}")


def _context_in(text: str | None, window: str) -> WindowContext | None:
    """The part of a text held in memory around ``window``, cut the way the repository cuts a stored text."""
    if not text:
        return None
    index = text.find(window)
    if index < 0:
        return None
    start = max(0, index - _CONTEXT_CHARS)
    return WindowContext(text=text[start : start + len(window) + 2 * _CONTEXT_CHARS], offset=index - start)
