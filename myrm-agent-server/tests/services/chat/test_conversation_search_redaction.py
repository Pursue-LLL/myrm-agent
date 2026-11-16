"""A credential in a conversation never reaches the model as a fragment, on the real service stack.

The agent reads conversation history through `search_sessions_corpus`, the production `ConversationHistorySearchProvider`
and the FTS recall index. FTS5 cuts its snippet out of the stored text, and a credential that the cut splits, or that
HTML escaping disguised, no longer matches the redactor's patterns. The provider therefore redacts the stored text the
snippet was cut from before it hands the snippet on, and hands it on as plain text: the text a person wrote, whatever
markup it holds.
"""

from __future__ import annotations

import hashlib

import pytest
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution import search_sessions_corpus
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import MemorySearchBackends
from myrm_agent_harness.toolkits.memory.conversation_search import ConversationSearchRequest
from myrm_agent_harness.toolkits.memory.conversation_search.types import ConversationSearchHit
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall import ConversationRecallRepository
from app.database.repositories.conversation_recall.sql import HIGHLIGHT_CLOSE, HIGHLIGHT_OPEN
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService
from app.services.chat.conversation_search_service import ConversationHistorySearchProvider, ConversationSearchService
from app.services.chat.conversation_search_snippet import redact_hit_windows
from tests.services.chat.search_support import seed_chat_with_text, shows_part_of

_VALUE = "Zk3Qm8Vt2Lp9Xw4R"
_TOKEN = "ghp_" + hashlib.sha256(b"search-redaction").hexdigest()[:36]
# Each form keeps its credential between quotes that an HTML-escaped copy turns into entities, which hides it from the
# redactor. The match sits next to the credential, so the window FTS5 cuts holds it.
_QUOTED_FORMS = {
    "json": 'cfg {"password": "%s"} kestrelmark ok',
    "env-double-quoted": 'rotate DB_PASSWORD="%s" before the kestrelmark cutover',
    "env-single-quoted": "rotate API_TOKEN='%s' before the kestrelmark cutover",
    "cli-flag": "kestrelmark first then psql --password '%s' -h db",
}
# Highlight tags a person typed. FTS5 puts its own highlight around the match and none of these is one, so each reads back
# as it was written.
_TYPED_TAGS = {
    "lowercase": "Wrap hits as <mark>kestrelmark</mark> in the results page",
    "uppercase": "Wrap hits as <MARK>kestrelmark</MARK> in the results page",
    "unpaired": "close the tag </mark> before kestrelmark ends",
}


async def _sessions(query: str, *, expand_conversation_id: str | None = None, expand_message_id: str | None = None) -> str:
    provider = ConversationHistorySearchProvider(current_chat_id=None, agent_id=None)
    result = await search_sessions_corpus(
        MemorySearchBackends(conversation_provider=provider),
        query=query,
        limit=5,
        since=None,
        until=None,
        expand_conversation_id=expand_conversation_id,
        expand_message_id=expand_message_id,
    )
    return str(result["content"]) if isinstance(result, dict) else result


async def _hit(query: str) -> ConversationSearchHit:
    response = await ConversationSearchService.search(ConversationSearchRequest(query=query, limit=3), agent_id=None)
    return response.hits[0]


def _display_snippet(hit: ConversationSearchHit) -> str:
    assert hit.source_ref is not None
    return hit.source_ref.snippet


@pytest.mark.parametrize("stored", _QUOTED_FORMS.values(), ids=_QUOTED_FORMS.keys())
@pytest.mark.asyncio
async def test_a_quoted_credential_in_the_window_is_masked_in_the_tool_output(fts_db: AsyncSession, stored: str) -> None:
    await seed_chat_with_text(fts_db, "chat-quoted", stored % _VALUE)

    hit = await _hit("kestrelmark")
    reply = await _sessions("kestrelmark")

    assert shows_part_of(_VALUE, _display_snippet(hit)), "the window FTS5 cut must hold the credential"
    assert not shows_part_of(_VALUE, hit.snippet)
    assert not shows_part_of(_VALUE, reply)
    assert "&quot;" not in reply
    assert "&#x27;" not in reply
    assert "kestrel" in hit.snippet


@pytest.mark.asyncio
async def test_a_vendor_token_that_the_window_cuts_is_masked_whole(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-token", f"{'filler words ' * 6}{_TOKEN} kestrelmark afterwards, and more to follow")

    hit = await _hit("kestrelmark")
    reply = await _sessions("kestrelmark")

    display = _display_snippet(hit)
    assert shows_part_of(_TOKEN, display), "the window FTS5 cut must reach into the token"
    assert _TOKEN not in display, "the window FTS5 cut must end inside the token"
    assert not shows_part_of(_TOKEN, hit.snippet)
    assert not shows_part_of(_TOKEN, reply)
    assert "kestrelmark" in hit.snippet


@pytest.mark.asyncio
async def test_a_credential_in_the_summary_is_masked(fts_db: AsyncSession) -> None:
    summary = 'Cutover plan: {"password": "%s"} then the kestrelmark window opens.' % _VALUE
    await seed_chat_with_text(fts_db, "chat-summary", "an unrelated question", summary=summary)

    hit = await _hit("kestrelmark")
    reply = await _sessions("kestrelmark")

    assert hit.summary == summary
    assert not shows_part_of(_VALUE, hit.snippet)
    assert not shows_part_of(_VALUE, reply)
    assert "kestrelmark" in hit.snippet


@pytest.mark.asyncio
async def test_a_credential_in_the_title_is_masked(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-title", "the kestrelmark rollout", title=f"deploy with {_TOKEN}")

    reply = await _sessions("kestrelmark")

    assert "deploy with" in reply
    assert not shows_part_of(_TOKEN, reply)


@pytest.mark.asyncio
async def test_the_short_keyword_fallback_masks_a_credential_its_cut_would_split(fts_db: AsyncSession) -> None:
    # A keyword under three characters is searched with LIKE, and its snippet is the first 100 characters of the message.
    await seed_chat_with_text(fts_db, "chat-short", "up " + "pad " * 21 + f"{_TOKEN} end")

    hit = await _hit("up")
    reply = await _sessions("up")

    display = _display_snippet(hit)
    assert shows_part_of(_TOKEN, display), "the 100-character cut must reach into the token"
    assert _TOKEN not in display, "the 100-character cut must end inside the token"
    assert not shows_part_of(_TOKEN, hit.snippet)
    assert not shows_part_of(_TOKEN, reply)


@pytest.mark.asyncio
async def test_an_expanded_message_masks_a_quoted_credential(fts_db: AsyncSession) -> None:
    message_ids = await seed_chat_with_text(fts_db, "chat-expand", f'cfg {{"password": "{_VALUE}"}} and done')

    reply = await _sessions("", expand_conversation_id="chat-expand", expand_message_id=message_ids[0])

    assert "and done" in reply
    assert not shows_part_of(_VALUE, reply)
    assert "&quot;" not in reply


@pytest.mark.asyncio
async def test_the_recent_listing_masks_a_quoted_credential(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-recent", f"cfg API_TOKEN='{_VALUE}' and done")

    reply = await _sessions("*")

    assert "and done" in reply
    assert not shows_part_of(_VALUE, reply)
    assert "&#x27;" not in reply


@pytest.mark.asyncio
async def test_the_model_reads_plain_text_while_the_display_reference_keeps_its_markup(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-markup", 'if a < b then "kestrelmark" wins')

    hit = await _hit("kestrelmark")

    assert hit.snippet == 'if a < b then "kestrelmark" wins'
    assert _display_snippet(hit) == "if a &lt; b then &quot;<mark>kestrelmark</mark>&quot; wins"


@pytest.mark.asyncio
async def test_the_ellipses_that_mark_a_cut_window_are_kept(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-cut", "lorem ipsum " * 20 + "kestrelmark" + " dolor sit" * 20)

    hit = await _hit("kestrelmark")

    assert hit.snippet.startswith("...")
    assert hit.snippet.endswith("...")
    assert hit.snippet == _display_snippet(hit).replace("<mark>", "").replace("</mark>", "")


@pytest.mark.asyncio
async def test_reasoning_tags_are_dropped_and_the_text_between_them_stays(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-think", "<think>weigh both options</think> kestrelmark is the pick")

    hit = await _hit("kestrelmark")

    assert "think>" not in hit.snippet
    assert "weigh both options kestrelmark is the pick" in hit.snippet


@pytest.mark.asyncio
async def test_a_window_that_spans_two_messages_is_read_from_the_transcript(fts_db: AsyncSession) -> None:
    message_ids = await seed_chat_with_text(fts_db, "chat-span", f"deploy key {_TOKEN}", "kestrelmark acknowledged")
    transcript = f"user: deploy key {_TOKEN}\nassistant: kestrelmark acknowledged"
    window = transcript[transcript.index(_TOKEN) + 12 :]
    hit = ConversationSearchHit(conversation_id="chat-span", message_id=message_ids[1], snippet=window, score=1.0)

    [rebuilt] = await redact_hit_windows([hit])

    assert "assistant: kestrelmark acknowledged" in rebuilt.snippet
    assert not shows_part_of(_TOKEN, rebuilt.snippet)


@pytest.mark.asyncio
async def test_a_window_found_in_no_stored_text_is_dropped_not_passed_on(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-gone", "something else entirely")
    hit = ConversationSearchHit(
        conversation_id="chat-gone", message_id="chat-gone-m1", snippet="a window nobody stored", score=1.0
    )

    [rebuilt] = await redact_hit_windows([hit])

    assert rebuilt.snippet == ""
    assert rebuilt.conversation_id == "chat-gone"


@pytest.mark.parametrize("stored", _TYPED_TAGS.values(), ids=_TYPED_TAGS.keys())
@pytest.mark.asyncio
async def test_highlight_tags_a_person_typed_are_read_back_as_written(fts_db: AsyncSession, stored: str) -> None:
    [message_id] = await seed_chat_with_text(fts_db, "chat-typed", stored)

    hit = await _hit("kestrelmark")
    recent = await _sessions("*")
    expanded = await _sessions("", expand_conversation_id="chat-typed", expand_message_id=message_id)
    picked, _total = await ConversationRecallIndexService.search_citable_chats("kestrelmark")

    # FTS5 may start its window after the "user: " the transcript opens with, and then marks the cut with an ellipsis.
    assert stored in hit.snippet
    assert f"snippet: {stored}" in recent
    assert f"snippet: user: {stored}" in expanded
    assert stored in str(picked[0]["snippet"])


@pytest.mark.asyncio
async def test_a_stored_text_holding_the_highlight_markers_gets_no_snippet(fts_db: AsyncSession) -> None:
    # Such a text cannot be told from the highlight FTS5 adds, so the window cannot be placed in it.
    await seed_chat_with_text(fts_db, "chat-markers", f"alpha {HIGHLIGHT_OPEN}beta{HIGHLIGHT_CLOSE} kestrelmark omega")

    hit = await _hit("kestrelmark")

    assert hit.snippet == ""


@pytest.mark.asyncio
async def test_a_search_row_carries_the_match_as_display_markup_and_as_plain_text(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-row", 'if a < b then "kestrelmark" wins')

    [row] = await ConversationRecallRepository.search(
        fts_db,
        safe_query="kestrelmark",
        limit=3,
        current_chat_id=None,
        agent_id=None,
        current_source=None,
        scope="all",
        lineage_chat_ids=[],
        since=None,
        until=None,
    )

    assert "<mark>kestrelmark</mark>" in row.snippet
    assert 'if a < b then "kestrelmark" wins' in row.window
    assert row.window == row.snippet.replace("<mark>", "").replace("</mark>", "")
    for marker in (HIGHLIGHT_OPEN, HIGHLIGHT_CLOSE):
        assert marker not in row.snippet + row.window


@pytest.mark.asyncio
async def test_a_chat_excluded_after_it_was_ranked_is_not_read_back_for_its_snippet(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-late", "the kestrelmark rollout notes")
    ranked = await _hit("kestrelmark")
    assert ranked.snippet == "the kestrelmark rollout notes"
    await ConversationRecallRepository.set_excluded(fts_db, "chat-late", True)
    await fts_db.commit()

    [rebuilt] = await redact_hit_windows([ranked])

    assert rebuilt.snippet == ""
