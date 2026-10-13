"""Chat history loading and message search mixin.

[INPUT]
- _base::_ChatServiceBase (POS: repository 协议和访问器)
- chat_helpers::filter_messages, _sanitize_snippet, ChannelHistoryEntry (POS: 消息过滤与格式化)
- chat_message_search_repo::MessageFtsSearchRow (POS: FTS5 搜索结果 DTO)

[OUTPUT]
- _ChatHistoryMixin: Web/Channel 历史加载、FTS5 消息搜索

[POS]
历史加载与搜索编排层。提供 Web/Channel 端历史消息加载（含 compaction summary 注入）
和 FTS5 全文搜索。
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase
from .chat_helpers import (
    ChannelHistoryEntry,
    _sanitize_snippet,
    filter_messages,
)

logger = logging.getLogger(__name__)


def _serialize_search_sent_at(value: datetime | str | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


class _ChatHistoryMixin(_ChatServiceBase):
    """History loading and message search operations."""

    @staticmethod
    async def load_web_chat_history(
        chat_id: str,
        exclude_message_id: str | None = None,
        max_messages: int = 50,
        api_key: str | None = None,
    ) -> list[list[str | dict[str, object]]]:
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id)
            history: list[list[str | dict[str, object]]] = []
            anchor_ts = None
            if chat and chat.compacted_summary and chat.compacted_before_id:
                history.append(
                    [
                        "assistant",
                        f"[Previous conversation summary]\n{chat.compacted_summary}",
                    ]
                )
                anchor_ts = await _ChatServiceBase._cr(uow).get_message_created_at(chat.compacted_before_id)
            all_messages = await _ChatServiceBase._cr(uow).get_recent_messages(
                chat_id,
                limit=max_messages,
                exclude_message_id=exclude_message_id,
                after_ts=anchor_ts,
            )

        filtered_messages = filter_messages(all_messages, api_key=api_key)
        for msg in filtered_messages:
            if msg.role == "user":
                sent_at = msg.sent_at
                if sent_at and sent_at.tzinfo is None:
                    from datetime import timezone

                    sent_at = sent_at.replace(tzinfo=timezone.utc)

                content = msg.content
                if msg.extra_data and "original_query" in msg.extra_data:
                    content = msg.extra_data["original_query"]

                meta = {
                    "sent_at": sent_at.timestamp() if sent_at else 0.0,
                    "sent_timezone": msg.sent_timezone,
                    "message_id": msg.id,
                    "chat_id": msg.chat_id,
                    "extra_data": msg.extra_data or {},
                }
                history.append(["human", content, meta])
            elif msg.role == "assistant":
                assistant_meta: dict[str, object] = {}
                if msg.extra_data:
                    reasoning = msg.extra_data.get("reasoning")
                    if isinstance(reasoning, str) and reasoning:
                        assistant_meta["reasoning_content"] = reasoning
                if assistant_meta:
                    history.append(["assistant", msg.content, assistant_meta])
                else:
                    history.append(["assistant", msg.content])
        return history

    @staticmethod
    async def load_channel_history(chat_id: str, max_messages: int = 50, api_key: str | None = None) -> list[ChannelHistoryEntry]:
        entries: list[ChannelHistoryEntry] = []
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id)
            anchor_ts = None
            if chat and chat.compacted_summary and chat.compacted_before_id:
                summary_created = chat.compacted_at or datetime.utcnow()
                entries.append(
                    ChannelHistoryEntry(
                        role="assistant",
                        content=f"[Previous conversation summary]\n{chat.compacted_summary}",
                        created_at=summary_created,
                    )
                )
                anchor_ts = await _ChatServiceBase._cr(uow).get_message_created_at(chat.compacted_before_id)
            all_messages = await _ChatServiceBase._cr(uow).get_recent_messages(chat_id, limit=max_messages, after_ts=anchor_ts)

        if not all_messages:
            return entries
        history_messages = filter_messages(all_messages[:-1], api_key=api_key)
        entries.extend(
            (
                ChannelHistoryEntry(
                    role="human" if msg.role == "user" else "assistant",
                    content=msg.content,
                    created_at=msg.created_at,
                )
                for msg in history_messages
            )
        )
        return entries

    @staticmethod
    async def search_messages(
        query: str,
        limit: int = 10,
        offset: int = 0,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        from myrm_agent_harness.utils.db.fts5 import sanitize_fts5_query

        safe_query = sanitize_fts5_query(query)
        if not safe_query:
            return ([], 0)
        try:
            async with UnitOfWork() as uow:
                raw_messages, total = await _ChatServiceBase._cr(uow).search_messages_fts(safe_query, limit, offset, since, until)
            messages: list[dict[str, object]] = [
                {
                    "id": msg["id"],
                    "chat_id": msg["chat_id"],
                    "role": msg["role"],
                    "content": msg["content"],
                    "sent_at": _serialize_search_sent_at(msg["sent_at"]),
                    "chat_title": msg["chat_title"],
                    "snippet": _sanitize_snippet(str(msg.get("highlight_snippet") or "")),
                }
                for msg in raw_messages
            ]
            return (messages, total)
        except Exception as e:
            logger.warning(f"FTS5 search failed for query '{query}': {e}")
            return ([], 0)
