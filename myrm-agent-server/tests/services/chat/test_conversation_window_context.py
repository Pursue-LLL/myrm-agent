"""``fetch_window_context`` returns the stored text around a snippet window, found and cut inside SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat
from app.database.repositories.conversation_recall import (
    ConversationRecallLookupRepository,
    ConversationRecallRepository,
    WindowContext,
)
from tests.services.chat.search_support import seed_chat_with_text

_STORED = "alpha bravo charlie delta echo foxtrot golf hotel india"
_WINDOW = "charlie delta"


async def _context(db: AsyncSession, chat_id: str, message_id: str | None, window: str, radius: int = 6) -> WindowContext | None:
    return await ConversationRecallLookupRepository.fetch_window_context(
        db, chat_id=chat_id, message_id=message_id, window=window, radius=radius
    )


@pytest.mark.asyncio
async def test_a_window_inside_a_message_comes_back_with_the_text_around_it(fts_db: AsyncSession) -> None:
    [message_id] = await seed_chat_with_text(fts_db, "chat-ctx", _STORED)

    context = await _context(fts_db, "chat-ctx", message_id, _WINDOW)

    # Six characters before the window, then the window and six characters after it.
    assert context == WindowContext(text="bravo charlie delta echo ", offset=6)


@pytest.mark.asyncio
async def test_the_context_stops_at_the_start_and_the_end_of_the_stored_text(fts_db: AsyncSession) -> None:
    [message_id] = await seed_chat_with_text(fts_db, "chat-edges", _STORED)

    # Where the start comes first, the room it leaves is added after the window.
    assert await _context(fts_db, "chat-edges", message_id, "alpha bravo") == WindowContext(
        text="alpha bravo charlie del", offset=0
    )
    assert await _context(fts_db, "chat-edges", message_id, "hotel india") == WindowContext(text=" golf hotel india", offset=6)


@pytest.mark.asyncio
async def test_a_window_spanning_two_messages_is_found_in_the_transcript(fts_db: AsyncSession) -> None:
    [first, second] = await seed_chat_with_text(fts_db, "chat-span", "first message ends here", "second one begins")
    window = "ends here\nassistant: second"

    in_a_message = await _context(fts_db, "chat-span", second, window, radius=0)
    transcript = await _context(fts_db, "chat-span", None, window, radius=0)

    assert in_a_message == WindowContext(text=window, offset=0)
    assert transcript == in_a_message
    assert first != second


@pytest.mark.asyncio
async def test_a_window_only_the_listed_latest_message_holds_is_found_in_the_document_snippet(fts_db: AsyncSession) -> None:
    fts_db.add(Chat(id="chat-legacy", title="Legacy", action_mode="agent", last_message="the legacy last message"))
    await fts_db.commit()
    await ConversationRecallRepository.rebuild_chat(fts_db, "chat-legacy")
    await fts_db.commit()

    assert await _context(fts_db, "chat-legacy", None, "legacy last", radius=4) == WindowContext(
        text="the legacy last mes", offset=4
    )


@pytest.mark.asyncio
async def test_a_window_no_stored_text_holds_comes_back_empty(fts_db: AsyncSession) -> None:
    [message_id] = await seed_chat_with_text(fts_db, "chat-none", _STORED)

    assert await _context(fts_db, "chat-none", message_id, "not stored anywhere") is None
    assert await _context(fts_db, "another-chat", message_id, _WINDOW) is None


@pytest.mark.asyncio
async def test_positions_count_characters_beyond_the_basic_plane_as_one(fts_db: AsyncSession) -> None:
    [message_id] = await seed_chat_with_text(fts_db, "chat-unicode", "密码 🔑 abc def 结束")

    context = await _context(fts_db, "chat-unicode", message_id, "abc def", radius=3)

    assert context == WindowContext(text=" 🔑 abc def 结束", offset=3)
