"""Chat search answers to the text that was typed, wherever it is typed.

The sidebar, the search dialog, the ``@chat:`` picker and the model's conversation search all fall back to a substring
scan when the trigram index has nothing (a query under three characters, or one the FTS expression flattens: ``C++``
becomes ``C``). That scan reads the typed text: punctuation is literal, ``%`` and ``_`` are not wildcards, a backslash is
a backslash, and a query with nothing searchable in it matches nothing (the sidebar then shows every chat).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from myrm_agent_harness.toolkits.memory.conversation_search.types import ConversationSearchRequest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.chat_message_search_repo import ChatMessageSearchRepository
from app.database.repositories.chat_repo import ChatRepository
from app.database.repositories.conversation_recall import ConversationRecallRepository
from app.services.chat.chat_service import ChatService
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService
from app.services.chat.conversation_search_service import ConversationSearchService
from tests.services.chat.search_support import seed_chat_with_text

_TARGET = "chat-target"
_DECOY = "chat-decoy"
# Other chats that hold the letters a short or flattened query is made of: a scan that reads the wrong text returns them.
_FILLERS = (
    "Quarterly checklist for the cache and the archive roadmap",
    "Extra yield summary for the sandbox rebuild every day",
    "Uncommon diary of a robust deployment during the review",
)
_Entry = Callable[[AsyncSession, str], Awaitable[set[str]]]
_RepoSearch = Callable[[AsyncSession, str, str], Awaitable[set[str]]]


async def _sidebar(db: AsyncSession, query: str) -> set[str]:
    chats, _total = await ChatRepository.get_chats_paginated(db, offset=0, limit=50, keyword=query)
    return {chat.id for chat in chats}


async def _dialog(_db: AsyncSession, query: str) -> set[str]:
    items, _total = await ChatService.search_messages(query, limit=50)
    return {str(item["chat_id"]) for item in items}


async def _picker(_db: AsyncSession, query: str) -> set[str]:
    items, _total = await ConversationRecallIndexService.search_citable_chats(query, limit=50)
    return {str(item["chat_id"]) for item in items}


async def _model(_db: AsyncSession, query: str) -> set[str]:
    response = await ConversationSearchService.search(ConversationSearchRequest(query=query, limit=8), agent_id=None)
    return {hit.conversation_id for hit in response.hits}


async def _sidebar_message_ids(db: AsyncSession, safe_query: str, raw_query: str) -> set[str]:
    return set(await ChatMessageSearchRepository.get_matching_chat_ids(db, safe_query, raw_query=raw_query))


async def _dialog_rows(db: AsyncSession, safe_query: str, raw_query: str) -> set[str]:
    rows, _total = await ChatMessageSearchRepository.search_messages_fts(db, safe_query, 50, 0, None, None, raw_query=raw_query)
    return {row["chat_id"] for row in rows}


async def _recall_rows(db: AsyncSession, safe_query: str, raw_query: str) -> set[str]:
    rows = await ConversationRecallRepository.search(
        db,
        safe_query=safe_query,
        raw_query=raw_query,
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


_ENTRIES = [
    pytest.param(_sidebar, id="sidebar"),
    pytest.param(_dialog, id="dialog"),
    pytest.param(_picker, id="picker"),
    pytest.param(_model, id="model"),
]
_MESSAGE_ENTRIES = _ENTRIES[1:]


async def _seed(db: AsyncSession, target_text: str, decoy_text: str | None = None) -> None:
    for number, filler in enumerate(_FILLERS):
        await seed_chat_with_text(db, f"chat-filler-{number}", filler, "ok")
    await seed_chat_with_text(db, _TARGET, target_text, "noted")
    if decoy_text is not None:
        await seed_chat_with_text(db, _DECOY, decoy_text, "noted")


def _saying(phrase: str) -> str:
    return f"We discussed {phrase} during the planning meeting yesterday"


@pytest.mark.parametrize("entry", _ENTRIES)
@pytest.mark.parametrize("query", ["a.", "U.", "'s", "C++", "C#", "R&D", "a, b", "x => y", "a\\b", "it's"])
@pytest.mark.asyncio
async def test_a_search_finds_the_chat_that_says_what_was_typed_and_no_other(
    fts_db: AsyncSession, entry: _Entry, query: str
) -> None:
    await _seed(fts_db, _saying(query))

    assert await entry(fts_db, query) == {_TARGET}


@pytest.mark.parametrize("entry", _ENTRIES)
@pytest.mark.asyncio
async def test_a_quoted_short_phrase_is_searched_without_its_quotes(fts_db: AsyncSession, entry: _Entry) -> None:
    await _seed(fts_db, _saying("ab"))

    assert await entry(fts_db, '"ab"') == {_TARGET}


@pytest.mark.parametrize(("query", "decoy"), [("a_", "ab"), ("50%", "500")])
@pytest.mark.parametrize("entry", _ENTRIES)
@pytest.mark.asyncio
async def test_percent_and_underscore_are_not_wildcards(fts_db: AsyncSession, entry: _Entry, query: str, decoy: str) -> None:
    await _seed(fts_db, _saying(query), decoy_text=_saying(decoy))

    assert await entry(fts_db, query) == {_TARGET}


@pytest.mark.asyncio
async def test_the_model_scans_the_typed_query_once_and_does_not_mark_its_answer_relaxed(fts_db: AsyncSession) -> None:
    """``ab cd`` plans a strict and a relaxed FTS query; the relaxed one only widens the FTS expression."""
    await _seed(fts_db, _saying("ab cd"))

    response = await ConversationSearchService.search(ConversationSearchRequest(query="ab cd", limit=8), agent_id=None)

    assert {hit.conversation_id for hit in response.hits} == {_TARGET}
    assert response.relaxed is False


@pytest.mark.parametrize("query", ['""', '" "'])
@pytest.mark.parametrize("entry", _MESSAGE_ENTRIES)
@pytest.mark.asyncio
async def test_a_query_with_nothing_searchable_matches_nothing(fts_db: AsyncSession, entry: _Entry, query: str) -> None:
    await _seed(fts_db, _saying("anything"))

    assert await entry(fts_db, query) == set()


@pytest.mark.parametrize("query", ['""', "   ", '" "'])
@pytest.mark.asyncio
async def test_the_sidebar_filters_nothing_when_nothing_searchable_was_typed(fts_db: AsyncSession, query: str) -> None:
    await _seed(fts_db, _saying("anything"))

    assert await _sidebar(fts_db, query) == {_TARGET, *(f"chat-filler-{number}" for number in range(len(_FILLERS)))}


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("docker", {"t-end", "t-comma"}),
        ("docker ", {"t-end", "t-comma"}),
        (" docker", {"t-end", "t-comma"}),
        ("C:\\Users\\me", {"t-path"}),
        ("50%", {"t-percent"}),
        ("_ud", {"t-underscore"}),
    ],
)
@pytest.mark.asyncio
async def test_the_sidebar_matches_titles_as_typed(fts_db: AsyncSession, query: str, expected: set[str]) -> None:
    titles = {
        "t-end": "Notes about docker",
        "t-comma": "docker, tips",
        "t-path": "C:\\Users\\me notes",
        "t-percent": "Saved 50% budget",
        "t-percent-decoy": "Saved 5000 budget",
        "t-underscore": "build_udf plan",
        "t-underscore-decoy": "Build udf plan",
    }
    for chat_id, title in titles.items():
        await seed_chat_with_text(fts_db, chat_id, "nothing relevant", title=title)

    assert await _sidebar(fts_db, query) == expected


@pytest.mark.parametrize(
    "search",
    [
        pytest.param(_sidebar_message_ids, id="sidebar"),
        pytest.param(_dialog_rows, id="dialog"),
        pytest.param(_recall_rows, id="recall"),
    ],
)
@pytest.mark.asyncio
async def test_the_substring_scan_reads_the_typed_text_and_not_the_fts_expression(
    fts_db: AsyncSession, search: _RepoSearch
) -> None:
    await _seed(fts_db, _saying("a."))

    assert await search(fts_db, '"zzzz"', "a.") == {_TARGET}
    assert await search(fts_db, '"a."', "zzzz") == set()
