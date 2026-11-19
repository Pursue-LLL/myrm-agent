"""The reads of the recall index that carry a time show the time of the message they name, on the real service stack.

The index keeps its timestamps as text in two forms (a rebuild copies a message's time as stored, an append binds the
caller's aware datetime) and the repository reads them through raw SQL, so a hit, the management list, the ``@chat:``
picker and the health summary each depend on turning that text into an instant. A search hit carries when the message it
names was sent, a recent hit when its conversation's last message was, the tool prints that time in the hit's header
(in the requester's zone when the request carries one) so the model can tell when a conversation happened, and a hit is
ranked by how well it matches, never by how old it is. A time no UTC instant can hold costs its hit the time, never the
search. The message window of an expanded hit carries no time.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

import pytest
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution import search_sessions_corpus
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import MemorySearchBackends
from myrm_agent_harness.toolkits.memory.conversation_search.types import ConversationSearchHit, ConversationSearchRequest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chats.chat.core.recall import list_conversation_recall_entries
from app.database.repositories.conversation_recall import ConversationRecallRow
from app.database.repositories.conversation_recall.types import recall_row
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService
from app.services.chat.conversation_search_hits import fts_hit, recent_hit
from app.services.chat.conversation_search_service import ConversationHistorySearchProvider, ConversationSearchService
from tests.services.chat.search_support import seed_chat_with_text

_CHAT = "chat-timed"
_UNREADABLE = "chat-unreadable"
_CREATED = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
_LAST = datetime(2026, 4, 20, 18, 45, 5, tzinfo=UTC)
_APPENDED = datetime(2026, 5, 1, 7, 8, 9, 125_000, tzinfo=UTC)
# Five hours behind UTC, the last second of 9999 is an instant UTC has no year for.
_PAST_UTC = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone(timedelta(hours=-5)))
# A requester's zone that is UTC+8 all year, so the offset a header shows is written out rather than looked up.
_ZONE = "Asia/Shanghai"
_ZONE_OFFSET = timezone(timedelta(hours=8))
# Message id to the time it was sent. The first message is the only one that says "zebra" or has "ze" in it.
_SENT = {
    f"{_CHAT}-m1": datetime(2026, 4, 2, 9, 30, 15, 250_000, tzinfo=UTC),
    f"{_CHAT}-m2": datetime(2026, 4, 2, 9, 31, 2, tzinfo=UTC),
    f"{_CHAT}-m3": _LAST,
}

# What a hit header ends with: the message a search hit names (a recent hit names none), then its time.
_HEADER_TAIL = re.compile(r"source: \w+(?:, message_id: (?P<message_id>[\w-]+))?, (?P<when>\S+)\)")

# A query under three characters has no trigram, so "ze" is answered by the substring scan.
_FTS = ConversationSearchRequest(query="zebra", limit=5)
_SUBSTRING = ConversationSearchRequest(query="ze", limit=5)
_RECENT = ConversationSearchRequest(mode="recent", limit=5)
_QUOKKA = ConversationSearchRequest(query="quokka", limit=5)


async def _seed(db: AsyncSession) -> None:
    """A conversation written weeks after it was created, whose last message is long after the first."""
    await seed_chat_with_text(
        db,
        _CHAT,
        "The zebra gateway needs a restart.",
        "Restarted it, everything is fine now.",
        "Thanks, closing this.",
        created_at=_CREATED,
        sent_at=list(_SENT.values()),
    )


async def _hits(request: ConversationSearchRequest) -> list[ConversationSearchHit]:
    return (await ConversationSearchService.search(request, agent_id=None)).hits


@pytest.mark.parametrize("request_", [_FTS, _SUBSTRING], ids=["fts", "substring-fallback"])
@pytest.mark.asyncio
async def test_a_search_hit_carries_the_send_time_of_the_message_it_names(
    fts_db: AsyncSession, request_: ConversationSearchRequest
) -> None:
    await _seed(fts_db)

    (hit,) = await _hits(request_)

    assert hit.conversation_id == _CHAT
    assert hit.message_id in _SENT
    assert hit.updated_at == _SENT[hit.message_id or ""]
    assert hit.created_at == _CREATED


@pytest.mark.asyncio
async def test_a_recent_hit_carries_the_time_of_the_last_message_of_its_conversation(fts_db: AsyncSession) -> None:
    await _seed(fts_db)

    (hit,) = await _hits(_RECENT)

    assert (hit.updated_at, hit.created_at) == (_LAST, _CREATED)


@pytest.mark.asyncio
async def test_a_message_appended_to_the_index_carries_its_own_time(fts_db: AsyncSession) -> None:
    await _seed(fts_db)
    await ConversationRecallIndexService.append_message(
        fts_db,
        chat_id=_CHAT,
        message_id="msg-appended",
        role="user",
        content="The quokka dashboard is live.",
        sent_at=_APPENDED,
    )
    await fts_db.commit()

    (found,) = await _hits(_QUOKKA)
    (recent,) = await _hits(_RECENT)

    assert (found.message_id, found.updated_at) == ("msg-appended", _APPENDED)
    assert recent.updated_at == _APPENDED


@pytest.mark.parametrize("zone", [None, _ZONE], ids=["utc", "requester-zone"])
@pytest.mark.parametrize("query", ["zebra", "*"], ids=["search", "recent"])
@pytest.mark.asyncio
async def test_the_header_and_the_source_card_show_the_time_of_what_the_hit_stands_for(
    fts_db: AsyncSession, query: str, zone: str | None
) -> None:
    await _seed(fts_db)
    backends = MemorySearchBackends(conversation_provider=ConversationHistorySearchProvider(current_chat_id=None, agent_id=None))

    result = await search_sessions_corpus(
        backends,
        query=query,
        limit=5,
        since=None,
        until=None,
        expand_conversation_id=None,
        expand_message_id=None,
        zone=zone,
    )

    assert isinstance(result, dict)
    header = _HEADER_TAIL.search(str(result["content"]))
    assert header is not None
    named = header["message_id"]
    stands_for = _SENT[named] if named else _LAST
    # The header writes the instant in the requester's zone (the last message crosses into the next day there).
    assert header["when"] == (stands_for if zone is None else stands_for.astimezone(_ZONE_OFFSET)).isoformat()
    # The card under the answer shows that one time, not when the conversation began.
    metadata = result["metadata"]
    assert isinstance(metadata, dict)
    (source,) = metadata["sources"]
    assert datetime.fromisoformat(source["updated_at"]) == stands_for
    assert "created_at" not in source


@pytest.mark.asyncio
async def test_a_time_utc_cannot_write_down_costs_its_hit_the_time_and_not_the_search(fts_db: AsyncSession) -> None:
    await _seed(fts_db)
    await seed_chat_with_text(fts_db, _UNREADABLE, "Standup notes.", created_at=_CREATED)
    await ConversationRecallIndexService.append_message(
        fts_db,
        chat_id=_UNREADABLE,
        message_id="msg-unreadable",
        role="user",
        content="The quokka dashboard is live.",
        sent_at=_PAST_UTC,
    )
    await fts_db.commit()

    (found,) = await _hits(_QUOKKA)
    (other,) = await _hits(_FTS)
    recent = {hit.conversation_id: hit for hit in await _hits(_RECENT)}

    assert (found.conversation_id, found.updated_at, found.created_at) == (_UNREADABLE, None, _CREATED)
    assert other.updated_at == _SENT[other.message_id or ""]
    assert (recent[_UNREADABLE].updated_at, recent[_CHAT].updated_at) == (None, _LAST)


def _row(**times: datetime) -> ConversationRecallRow:
    return recall_row({"chat_id": "chat-1", "source": "web", "snippet": "text", "rank": -3.0, **times})


def _search_score(row: ConversationRecallRow) -> float:
    return fts_hit(row, 2, 10, None).score


def _recent_score(row: ConversationRecallRow) -> float:
    return recent_hit(row, 2, None).score


@pytest.mark.parametrize("score", [_search_score, _recent_score], ids=["search", "recent"])
def test_a_hit_is_scored_by_relevance_whatever_time_it_carries(score: Callable[[ConversationRecallRow], float]) -> None:
    now = datetime.now(UTC)
    fresh = _row(last_message_at=now - timedelta(days=1), created_at=now - timedelta(days=40))
    stale = _row(last_message_at=now - timedelta(days=900), created_at=now - timedelta(days=900))
    timeless = _row()

    assert score(fresh) == score(stale) == score(timeless)


@pytest.mark.asyncio
async def test_the_management_list_shows_when_each_conversation_last_had_a_message(fts_db: AsyncSession) -> None:
    await _seed(fts_db)

    response = await list_conversation_recall_entries(excluded=None, page=1, page_size=20)

    (item,) = json.loads(bytes(response.body))["data"]["items"]
    assert item["last_message_at"] == _LAST.isoformat()
    # The panel shows one time; the index's own bookkeeping times are not part of the list.
    assert set(item) == {"chat_id", "title", "agent_id", "source", "snippet", "summary", "last_message_at", "is_excluded"}


@pytest.mark.asyncio
async def test_the_picker_shows_when_the_message_it_names_was_sent(fts_db: AsyncSession) -> None:
    await _seed(fts_db)

    items, total = await ConversationRecallIndexService.search_citable_chats("zebra")

    assert total == 1
    assert items[0]["sent_at"] == _SENT[str(items[0]["id"])].isoformat()


@pytest.mark.asyncio
async def test_the_health_summary_shows_when_the_index_was_last_written(fts_db: AsyncSession) -> None:
    await _seed(fts_db)

    health = await ConversationRecallIndexService.health()

    last_indexed_at = health["last_indexed_at"]
    assert isinstance(last_indexed_at, str)
    # The database stamps the write in UTC: read in any other zone it would be hours away from now.
    assert abs(datetime.now(UTC) - datetime.fromisoformat(last_indexed_at)) < timedelta(minutes=5)
