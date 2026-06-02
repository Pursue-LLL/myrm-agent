"""Shared Context history promotion service.

[INPUT]
app.database.models::Message (POS: 会话与消息域模型)
app.services.chat.chat_service::ChatService (POS: 聊天业务门面类)

[OUTPUT]
SharedContextHistoryService: 会话历史搜索和 Shared Context 提案来源解析
prepare_history_proposal_content: 历史消息到提案内容的边界处理
build_history_proposal_metadata: 历史消息来源审计元数据构建

[POS]
共享上下文历史证据服务。把会话历史检索结果转换为可审批的 Shared Context 写入提案来源。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.services.chat.chat_service import ChatService

MAX_HISTORY_PROPOSAL_CONTENT_CHARS = 4000


@dataclass(frozen=True, slots=True)
class SharedContextHistoryHit:
    """Search hit returned from chat history FTS."""

    message_id: str
    chat_id: str
    role: str
    content: str
    snippet: str
    chat_title: str
    sent_at: str | None


@dataclass(frozen=True, slots=True)
class SharedContextHistorySource:
    """Source message selected for promotion."""

    message_id: str
    chat_id: str
    role: str
    content: str
    chat_title: str
    sent_at: datetime | None


def _text_field(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _optional_text_field(row: dict[str, object], key: str) -> str | None:
    value = _text_field(row, key)
    return value or None


def prepare_history_proposal_content(content: str) -> tuple[str, bool]:
    """Normalize a source message for proposal storage without exceeding API limits."""
    normalized = content.strip()
    if not normalized:
        raise ValueError("History message content is empty")
    if len(normalized) <= MAX_HISTORY_PROPOSAL_CONTENT_CHARS:
        return normalized, False
    return normalized[:MAX_HISTORY_PROPOSAL_CONTENT_CHARS], True


def build_history_proposal_metadata(
    source: SharedContextHistorySource,
    *,
    extra_metadata: dict[str, object] | None = None,
    content_truncated: bool = False,
) -> dict[str, object]:
    """Build immutable source metadata for a history-derived write proposal."""
    metadata = dict(extra_metadata or {})
    metadata.update(
        {
            "promoted_from_history": True,
            "source_chat_id": source.chat_id,
            "source_message_id": source.message_id,
            "source_role": source.role,
            "source_chat_title": source.chat_title,
            "source_content_truncated": content_truncated,
        }
    )
    if source.sent_at is not None:
        metadata["source_sent_at"] = source.sent_at.isoformat()
    return metadata


class SharedContextHistoryService:
    """Search chat history and resolve selected messages for Shared Context proposals."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_messages(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[SharedContextHistoryHit], int]:
        rows, total = await ChatService.search_messages(query, limit=limit, offset=offset, since=since, until=until)
        hits = [
            SharedContextHistoryHit(
                message_id=_text_field(row, "id"),
                chat_id=_text_field(row, "chat_id"),
                role=_text_field(row, "role"),
                content=_text_field(row, "content"),
                snippet=_text_field(row, "snippet"),
                chat_title=_text_field(row, "chat_title"),
                sent_at=_optional_text_field(row, "sent_at"),
            )
            for row in rows
        ]
        return hits, total

    async def get_message(self, message_id: str) -> SharedContextHistorySource | None:
        stmt = (
            select(
                Message.id,
                Message.chat_id,
                Message.role,
                Message.content,
                Message.sent_at,
                Chat.title,
            )
            .join(Chat, Chat.id == Message.chat_id)
            .where(Message.id == message_id)
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return SharedContextHistorySource(
            message_id=row.id,
            chat_id=row.chat_id,
            role=row.role,
            content=row.content,
            chat_title=row.title or "",
            sent_at=row.sent_at,
        )
