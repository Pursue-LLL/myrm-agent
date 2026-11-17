"""When the FTS5 query itself fails, the sidebar still answers from the typed text and no log line repeats what was typed."""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.chat_message_search_repo import ChatMessageSearchRepository, MessageFtsSearchRow
from app.database.repositories.chat_repo import ChatRepository
from app.database.repositories.chat_repo.common import logger as chat_repo_logger
from app.services.chat.chat_service import ChatService
from tests.services.chat.search_support import seed_chat_with_text


async def _break_the_fts_index(db: AsyncSession) -> None:
    """Make every ``messages_fts`` query fail, as a corrupt or half-rebuilt index does."""
    await db.execute(text("DROP TABLE messages_fts"))
    await db.commit()


@pytest.mark.asyncio
async def test_the_sidebar_reads_the_typed_text_when_the_fts_query_fails(
    fts_db: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    await seed_chat_with_text(fts_db, "chat-target", "We moved the 沙箱部署 plan to Friday", "noted")
    await seed_chat_with_text(fts_db, "chat-other", "Nothing about it", "noted")
    await _break_the_fts_index(fts_db)

    with caplog.at_level(logging.WARNING, logger="app.database.repositories.chat_message_search_repo"):
        chats, _total = await ChatRepository.get_chats_paginated(fts_db, offset=0, limit=50, keyword="沙箱")

    assert {chat.id for chat in chats} == {"chat-target"}
    assert "falling back to the substring scan" in caplog.text


@pytest.mark.asyncio
async def test_the_sidebar_logs_a_failed_fts_lookup_without_the_typed_text(
    fts_db: AsyncSession, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def failing_lookup(*_args: object, **_kwargs: object) -> list[str]:
        raise RuntimeError("fts5: syntax error")

    monkeypatch.setattr(ChatMessageSearchRepository, "get_matching_chat_ids", staticmethod(failing_lookup))

    with caplog.at_level(logging.DEBUG, logger=chat_repo_logger.name):
        chats, total = await ChatRepository.get_chats_paginated(fts_db, offset=0, limit=50, keyword="hunter2 correct horse")

    assert (chats, total) == ([], 0)
    assert "fts5: syntax error" in caplog.text
    assert "hunter2" not in caplog.text


@pytest.mark.asyncio
async def test_the_search_dialog_logs_a_failed_fts_query_without_the_typed_text(
    fts_db: AsyncSession, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def failing_search(*_args: object, **_kwargs: object) -> tuple[list[MessageFtsSearchRow], int]:
        raise RuntimeError("fts5: syntax error")

    monkeypatch.setattr(ChatMessageSearchRepository, "search_messages_fts", staticmethod(failing_search))

    with caplog.at_level(logging.WARNING, logger="app.services.chat.chat_history"):
        items, total = await ChatService.search_messages("hunter2 correct horse", limit=10)

    assert (items, total) == ([], 0)
    assert "FTS5 message search failed" in caplog.text
    assert "fts5: syntax error" in caplog.text
    assert "hunter2" not in caplog.text
