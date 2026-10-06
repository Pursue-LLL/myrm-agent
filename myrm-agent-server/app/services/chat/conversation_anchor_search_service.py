"""Conversation anchor search service with exact phrase matching and highlight offsets.

[INPUT]
myrm_agent_harness.toolkits.memory::ContextHighlight (POS: 高亮切片模型)
myrm_agent_harness.toolkits.memory::ConversationExactSearchMatcher (POS: 短语与上下文提取匹配器)
app.database.repositories.uow::UnitOfWork (POS: 工作单元仓储)
app.services.chat._base::_ChatServiceBase (POS: 聊天仓储访问器基类)
app.schemas.anchor_search::ConversationAnchorSearchHit (POS: 锚点定位命中文档模型)

[OUTPUT]
ConversationAnchorSearchService: Exact phrase matching and anchor highlight scroll targeting provider.

[POS]
会话精确定位与高亮搜索业务服务。协调 FTS5 粗排检索与 Harness 短语精确匹配器，为前端会话直达与荧光闪烁锚点（pulse glow）提供字符偏移与上下文窗口切片。
"""

from __future__ import annotations

import logging
from datetime import datetime

from myrm_agent_harness.toolkits.memory import (
    ContextHighlight,
    ConversationExactSearchMatcher,
)
from myrm_agent_harness.utils.db.fts5 import sanitize_fts5_query

from app.database.repositories.uow import UnitOfWork
from app.schemas.anchor_search import (
    ConversationAnchorHighlightPayload,
    ConversationAnchorSearchHit,
)
from app.services.chat._base import _ChatServiceBase

logger = logging.getLogger(__name__)


def _serialize_timestamp(value: datetime | str | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _build_highlight_payload(hl: ContextHighlight) -> ConversationAnchorHighlightPayload:
    return ConversationAnchorHighlightPayload(
        prefix=hl.prefix,
        matched_text=hl.matched_text,
        suffix=hl.suffix,
        start_char=hl.start_char,
        end_char=hl.end_char,
        formatted_snippet=hl.formatted_snippet(),
    )


class ConversationAnchorSearchService(_ChatServiceBase):
    """Business service for conversation exact phrase matching and scroll anchor generation."""

    @classmethod
    async def search_anchors(
        cls,
        query: str,
        *,
        chat_id: str | None = None,
        limit: int = 20,
        window_chars: int = 100,
    ) -> list[ConversationAnchorSearchHit]:
        """Search messages with exact phrase highlight and character boundary offsets."""
        if not query or not query.strip():
            return []

        clean_query = query.strip()
        hits: list[ConversationAnchorSearchHit] = []

        try:
            async with UnitOfWork() as uow:
                repo = cls._cr(uow)

                if chat_id:
                    # In-session targeted search across entire message history
                    chat = await repo.get_chat_by_id(chat_id)
                    chat_title = chat.title if chat else None
                    messages = await repo.get_all_messages(chat_id)

                    for msg in messages:
                        content = getattr(msg, "content", "") or ""
                        if not content:
                            continue

                        if not ConversationExactSearchMatcher.matches(content, clean_query):
                            continue

                        hl = ConversationExactSearchMatcher.extract_highlight(
                            content, clean_query, window_chars=window_chars
                        )
                        if hl is None:
                            continue

                        score = ConversationExactSearchMatcher.rank_and_score(content, clean_query)
                        hits.append(
                            ConversationAnchorSearchHit(
                                chat_id=chat_id,
                                message_id=str(getattr(msg, "id", "")),
                                role=str(getattr(msg, "role", "unknown")),
                                score=score,
                                highlight=_build_highlight_payload(hl),
                                chat_title=chat_title,
                                sent_at=_serialize_timestamp(getattr(msg, "created_at", None)),
                            )
                        )
                else:
                    # Global cross-session search: use FTS5 candidate pre-filtering
                    safe_query = sanitize_fts5_query(clean_query)
                    raw_messages: list[dict[str, object]] = []
                    if safe_query:
                        raw_messages, _ = await repo.search_messages_fts(
                            safe_query, limit=max(limit * 3, 50), offset=0
                        )

                    for raw_msg in raw_messages:
                        content = str(raw_msg.get("content") or "")
                        if not content:
                            continue

                        if not ConversationExactSearchMatcher.matches(content, clean_query):
                            continue

                        hl = ConversationExactSearchMatcher.extract_highlight(
                            content, clean_query, window_chars=window_chars
                        )
                        if hl is None:
                            continue

                        score = ConversationExactSearchMatcher.rank_and_score(content, clean_query)
                        hits.append(
                            ConversationAnchorSearchHit(
                                chat_id=str(raw_msg.get("chat_id") or ""),
                                message_id=str(raw_msg.get("id") or ""),
                                role=str(raw_msg.get("role") or "unknown"),
                                score=score,
                                highlight=_build_highlight_payload(hl),
                                chat_title=str(raw_msg.get("chat_title")) if raw_msg.get("chat_title") else None,
                                sent_at=_serialize_timestamp(raw_msg.get("sent_at")),  # type: ignore[arg-type]
                            )
                        )

        except Exception as e:
            logger.warning(f"Conversation anchor search failed for query '{clean_query}': {e}", exc_info=True)
            return []

        # Sort descending by relevance score
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]
