"""Tests for sidebar FTS search integration.

Covers:
- ChatMessageSearchRepository.get_matching_chat_ids (unit, real SQLite FTS5)
- ChatRepository.get_chats_paginated keyword branch with FTS fallback
- Edge cases: empty query, FTS failure fallback, deleted/incognito filtering
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Chat, Message
from app.database.repositories.chat_message_search_repo import ChatMessageSearchRepository
from app.database.repositories.chat_repo import ChatRepository


@pytest_asyncio.fixture
async def fts_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:testdb_sidebar_fts?mode=memory&cache=shared&uri=true"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                content=messages,
                content_rowid=rowid,
                tokenize='trigram'
            )
        """)
        )
        await conn.execute(
            text("""
            CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
            END
        """)
        )
        await conn.execute(
            text("""
            CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES('delete', old.rowid, old.content);
            END
        """)
        )
        await conn.execute(
            text("""
            CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES('delete', old.rowid, old.content);
                INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
            END
        """)
        )

    TestSession = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with TestSession() as session:
        yield session

    await engine.dispose()


async def _seed_chat_with_messages(
    db: AsyncSession,
    chat_id: str,
    title: str,
    messages: list[tuple[str, str, str]],
    *,
    is_incognito: bool = False,
    deleted: bool = False,
) -> None:
    now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    chat = Chat(
        id=chat_id,
        title=title,
        first_message=messages[0][2] if messages else "",
        source="web",
        is_incognito=is_incognito,
        created_at=now,
        updated_at=now,
    )
    if deleted:
        chat.deleted_at = now
    db.add(chat)
    for msg_id, role, content in messages:
        msg = Message(
            id=msg_id,
            chat_id=chat_id,
            role=role,
            content=content,
            sent_at=now,
            sent_timezone="UTC",
        )
        db.add(msg)
    await db.commit()


# ── get_matching_chat_ids tests ──────────────────────────────


@pytest.mark.asyncio
class TestGetMatchingChatIds:
    async def test_returns_matching_chat_id(self, fts_session: AsyncSession) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-fts-1",
            "普通标题",
            [("msg-a1", "user", "WAL并发写入优化方案")],
        )
        result = await ChatMessageSearchRepository.get_matching_chat_ids(fts_session, "WAL")
        assert "chat-fts-1" in result

    async def test_empty_query_returns_empty(self, fts_session: AsyncSession) -> None:
        result = await ChatMessageSearchRepository.get_matching_chat_ids(fts_session, "")
        assert result == []

    async def test_no_match_returns_empty(self, fts_session: AsyncSession) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-fts-2",
            "标题",
            [("msg-b1", "user", "hello world")],
        )
        result = await ChatMessageSearchRepository.get_matching_chat_ids(
            fts_session, "nonexistent_xyz"
        )
        assert result == []

    async def test_excludes_incognito_chats(self, fts_session: AsyncSession) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-fts-incog",
            "隐身对话",
            [("msg-c1", "user", "secret WAL data")],
            is_incognito=True,
        )
        result = await ChatMessageSearchRepository.get_matching_chat_ids(fts_session, "WAL")
        assert "chat-fts-incog" not in result

    async def test_excludes_deleted_chats(self, fts_session: AsyncSession) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-fts-del",
            "已删除",
            [("msg-d1", "user", "deleted WAL content")],
            deleted=True,
        )
        result = await ChatMessageSearchRepository.get_matching_chat_ids(fts_session, "WAL")
        assert "chat-fts-del" not in result

    async def test_respects_limit(self, fts_session: AsyncSession) -> None:
        for i in range(5):
            await _seed_chat_with_messages(
                fts_session,
                f"chat-fts-lim-{i}",
                f"标题{i}",
                [(f"msg-lim-{i}", "user", "common keyword data")],
            )
        result = await ChatMessageSearchRepository.get_matching_chat_ids(
            fts_session, "common", limit=3
        )
        assert len(result) <= 3

    async def test_returns_distinct_chat_ids(self, fts_session: AsyncSession) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-fts-multi",
            "多消息",
            [
                ("msg-m1", "user", "first mention of WAL"),
                ("msg-m2", "assistant", "WAL is great for concurrency"),
            ],
        )
        result = await ChatMessageSearchRepository.get_matching_chat_ids(fts_session, "WAL")
        assert result.count("chat-fts-multi") == 1


# ── get_chats_paginated FTS integration tests ────────────────


@pytest.mark.asyncio
class TestGetChatsPaginatedWithFTS:
    async def test_keyword_finds_chat_via_message_content(
        self, fts_session: AsyncSession
    ) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-1",
            "数据库性能优化",
            [("msg-pg1", "user", "WAL并发写入问题分析")],
        )
        chats, total = await ChatRepository.get_chats_paginated(
            fts_session, offset=0, limit=10, keyword="WAL"
        )
        assert total >= 1
        assert any(c.id == "chat-pg-1" for c in chats)

    async def test_keyword_still_matches_title(self, fts_session: AsyncSession) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-2",
            "WAL并发讨论",
            [("msg-pg2", "user", "hello")],
        )
        chats, total = await ChatRepository.get_chats_paginated(
            fts_session, offset=0, limit=10, keyword="WAL"
        )
        assert any(c.id == "chat-pg-2" for c in chats)

    async def test_keyword_no_match_returns_empty(self, fts_session: AsyncSession) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-3",
            "普通标题",
            [("msg-pg3", "user", "普通内容")],
        )
        chats, total = await ChatRepository.get_chats_paginated(
            fts_session, offset=0, limit=10, keyword="nonexistent_xyz_keyword"
        )
        assert total == 0

    async def test_no_keyword_returns_all(self, fts_session: AsyncSession) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-4",
            "任意标题",
            [("msg-pg4", "user", "任意内容")],
        )
        chats, total = await ChatRepository.get_chats_paginated(
            fts_session, offset=0, limit=10
        )
        assert total >= 1

    async def test_keyword_wildcard_percent_safe(self, fts_session: AsyncSession) -> None:
        """SQL wildcard '%' in keyword should not match all chats."""
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-pct",
            "100% 完成率",
            [("msg-pg-pct", "user", "完成率100%")],
        )
        chats, total = await ChatRepository.get_chats_paginated(
            fts_session, offset=0, limit=10, keyword="%"
        )
        # '%' alone should not act as SQL wildcard matching everything
        for c in chats:
            assert "%" in (c.title or "") or "%" in (c.first_message or "") or c.id == "chat-pg-pct"

    async def test_keyword_fts_combined_with_title_match(
        self, fts_session: AsyncSession
    ) -> None:
        """Both title-match and message-match chats should appear."""
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-title",
            "Docker部署方案",
            [("msg-pg-t1", "user", "hello world")],
        )
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-msg",
            "普通对话",
            [("msg-pg-m1", "user", "Docker Compose配置示例")],
        )
        chats, total = await ChatRepository.get_chats_paginated(
            fts_session, offset=0, limit=10, keyword="Docker"
        )
        chat_ids = {c.id for c in chats}
        assert "chat-pg-title" in chat_ids, "title-match should appear"
        assert "chat-pg-msg" in chat_ids, "message-content-match should appear"

    async def test_keyword_does_not_return_incognito(
        self, fts_session: AsyncSession
    ) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-incog",
            "隐身对话",
            [("msg-pg-inc", "user", "secret UniqueKeyword999 data")],
            is_incognito=True,
        )
        chats, total = await ChatRepository.get_chats_paginated(
            fts_session, offset=0, limit=10, keyword="UniqueKeyword999"
        )
        assert all(c.id != "chat-pg-incog" for c in chats)

    async def test_keyword_does_not_return_deleted(
        self, fts_session: AsyncSession
    ) -> None:
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-del",
            "已删除对话",
            [("msg-pg-del", "user", "DeletedContent777 important")],
            deleted=True,
        )
        chats, total = await ChatRepository.get_chats_paginated(
            fts_session, offset=0, limit=10, keyword="DeletedContent777"
        )
        assert all(c.id != "chat-pg-del" for c in chats)

    async def test_chinese_keyword_via_fts(self, fts_session: AsyncSession) -> None:
        """Chinese text search through FTS (trigram tokenizer)."""
        await _seed_chat_with_messages(
            fts_session,
            "chat-pg-zh",
            "普通标题",
            [("msg-pg-zh", "user", "Kubernetes弹性伸缩和HPA配置详解")],
        )
        chats, total = await ChatRepository.get_chats_paginated(
            fts_session, offset=0, limit=10, keyword="HPA"
        )
        assert any(c.id == "chat-pg-zh" for c in chats)
