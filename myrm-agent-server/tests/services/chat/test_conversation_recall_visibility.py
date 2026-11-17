"""Which chats conversation recall hands to the model, read by read.

A chat the user excluded and a web incognito chat do not come back from any of these reads: a search (both FTS tiers and
the LIKE fallback), the recent list, an expanded message window, the stored text a snippet window is cut from, or the
``@chat:`` picker. A transcript import carries the incognito flag only to stay out of the sidebar, so it stays readable. The flag lives
on ``chats`` and a chat can change it after it was indexed, so each read decides from the flag's current value.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import pytest
from myrm_agent_harness.toolkits.memory.conversation_search import ConversationSearchRequest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall import (
    ConversationRecallLookupRepository,
    ConversationRecallRepository,
)
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService
from app.services.chat.conversation_search_service import ConversationSearchService
from tests.services.chat.search_support import seed_chat_with_text

_OPEN = "chat-open"
_PRIVATE = "chat-private"
_IMPORTED = "chat-imported"
_EXCLUDED = "chat-excluded"
_ALL = (_OPEN, _PRIVATE, _IMPORTED, _EXCLUDED)
_READABLE = {_OPEN, _IMPORTED}

_TERM = "quillfeather"
# Two characters have no trigram, so only the LIKE fallback can match this one.
_SHORT = "kq"
_BODY = f"{_TERM} {_SHORT} notes in"
_RECALL_LOGGER = "app.database.repositories.conversation_recall.repo"

_Reader = Callable[[AsyncSession], Awaitable[set[str]]]


async def _seed(db: AsyncSession) -> None:
    await seed_chat_with_text(db, _OPEN, f"{_BODY} {_OPEN}")
    await seed_chat_with_text(db, _PRIVATE, f"{_BODY} {_PRIVATE}", is_incognito=True)
    await seed_chat_with_text(db, _IMPORTED, f"{_BODY} {_IMPORTED}", is_incognito=True, source="external:claude_code")
    await seed_chat_with_text(db, _EXCLUDED, f"{_BODY} {_EXCLUDED}")
    await ConversationRecallRepository.set_excluded(db, _EXCLUDED, True)
    await db.commit()


async def _set_incognito(db: AsyncSession, chat_id: str, incognito: bool) -> None:
    await db.execute(text("UPDATE chats SET is_incognito = :flag WHERE id = :chat_id"), {"flag": incognito, "chat_id": chat_id})
    await db.commit()


async def _search(_db: AsyncSession) -> set[str]:
    response = await ConversationSearchService.search(ConversationSearchRequest(query=_TERM, limit=8), agent_id=None)
    return {hit.conversation_id for hit in response.hits}


async def _like_fallback(db: AsyncSession) -> set[str]:
    rows = await ConversationRecallRepository.search(
        db,
        safe_query=_SHORT,
        raw_query=_SHORT,
        limit=10,
        current_chat_id=None,
        agent_id=None,
        current_source=None,
        scope="all",
        lineage_chat_ids=[],
        since=None,
        until=None,
    )
    return {row.chat_id for row in rows}


async def _recent(_db: AsyncSession) -> set[str]:
    response = await ConversationSearchService.search(ConversationSearchRequest(limit=8), agent_id=None)
    return {hit.conversation_id for hit in response.hits}


async def _expanded(_db: AsyncSession) -> set[str]:
    opened: set[str] = set()
    for chat_id in _ALL:
        request = ConversationSearchRequest(expand_conversation_id=chat_id, expand_message_id=f"{chat_id}-m1")
        if (await ConversationSearchService.search(request, agent_id=None)).hits:
            opened.add(chat_id)
    return opened


async def _window_text(db: AsyncSession) -> set[str]:
    found: set[str] = set()
    for chat_id in _ALL:
        context = await ConversationRecallLookupRepository.fetch_window_context(
            db, chat_id=chat_id, message_id=f"{chat_id}-m1", window=_TERM, radius=10
        )
        if context is not None:
            found.add(chat_id)
    return found


async def _picker(_db: AsyncSession) -> set[str]:
    items, _total = await ConversationRecallIndexService.search_citable_chats(_TERM, limit=10)
    return {str(item["chat_id"]) for item in items}


_READERS: dict[str, _Reader] = {
    "search": _search,
    "like-fallback": _like_fallback,
    "recent": _recent,
    "expand": _expanded,
    "window-text": _window_text,
    "picker": _picker,
}


@pytest.mark.parametrize("read", _READERS.values(), ids=_READERS.keys())
@pytest.mark.asyncio
async def test_only_the_open_and_the_imported_chat_are_read(fts_db: AsyncSession, read: _Reader) -> None:
    await _seed(fts_db)

    assert await read(fts_db) == _READABLE


@pytest.mark.parametrize("read", _READERS.values(), ids=_READERS.keys())
@pytest.mark.asyncio
async def test_the_incognito_flag_is_read_when_the_query_runs(fts_db: AsyncSession, read: _Reader) -> None:
    await _seed(fts_db)

    await _set_incognito(fts_db, _PRIVATE, False)
    assert await read(fts_db) == {*_READABLE, _PRIVATE}

    await _set_incognito(fts_db, _PRIVATE, True)
    assert await read(fts_db) == _READABLE


@pytest.mark.asyncio
async def test_no_statement_falls_back_to_a_degraded_search(fts_db: AsyncSession, caplog: pytest.LogCaptureFixture) -> None:
    await _seed(fts_db)

    # A statement that fails is logged and skipped, so a broken filter would look like a search that finds less.
    with caplog.at_level(logging.WARNING, logger=_RECALL_LOGGER):
        for read in (_search, _like_fallback, _recent):
            assert await read(fts_db) == _READABLE

    assert [record.getMessage() for record in caplog.records if record.name == _RECALL_LOGGER] == []
