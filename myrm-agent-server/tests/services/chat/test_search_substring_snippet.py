"""A hit found by the substring scan is previewed like one found by the trigram index: a window of the same width, centred
on the match, with the match marked and ``...`` where the text goes on.

The scan stands in for the index when the query is under three characters. Against the real index the window is pinned
only for a lone match at the start, middle or end of a text padded with plain characters; elsewhere FTS5 may start its
window at a different character (see ``substring_snippet``).
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.utils.db.fts5 import sanitize_fts5_query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.chat_message_search_repo import ChatMessageSearchRepository
from app.services.chat.chat_service import ChatService
from tests.services.chat.search_support import seed_chat_with_text

_WINDOW = 42  # what FTS5 snippet() cuts with 40 trigram tokens
_BEFORE = "前文" * 40
_AFTER = "后文" * 40


async def _preview(db: AsyncSession, content: str, query: str) -> str:
    """The dialog row's preview of the one message in ``content`` that holds ``query``."""
    await seed_chat_with_text(db, "chat-preview", content, "ok")
    rows, total = await ChatMessageSearchRepository.search_messages_fts(
        db, sanitize_fts5_query(query), 50, 0, None, None, raw_query=query
    )
    assert total == 1
    return rows[0]["highlight_snippet"] or ""


@pytest.mark.asyncio
async def test_a_match_deep_in_a_long_message_is_centred_in_its_window(fts_db: AsyncSession) -> None:
    preview = await _preview(fts_db, f"{_BEFORE}部署{_AFTER}", "部署")

    assert preview == f"...{_BEFORE[-20:]}<mark>部署</mark>{_AFTER[:20]}..."


@pytest.mark.asyncio
async def test_a_match_near_the_start_keeps_the_window_full_and_opens_without_an_ellipsis(fts_db: AsyncSession) -> None:
    preview = await _preview(fts_db, f"前言部署{_AFTER}", "部署")

    assert preview == f"前言<mark>部署</mark>{_AFTER[:38]}..."


@pytest.mark.asyncio
async def test_a_match_near_the_end_keeps_the_window_full_and_closes_without_an_ellipsis(fts_db: AsyncSession) -> None:
    preview = await _preview(fts_db, f"{_BEFORE}部署完毕", "部署")

    assert preview == f"...{_BEFORE[-38:]}<mark>部署</mark>完毕"


@pytest.mark.asyncio
async def test_a_short_message_is_shown_whole_with_the_match_marked(fts_db: AsyncSession) -> None:
    assert await _preview(fts_db, "请检查部署状态", "部署") == "请检查<mark>部署</mark>状态"


@pytest.mark.asyncio
async def test_the_marked_text_keeps_the_case_of_the_message(fts_db: AsyncSession) -> None:
    assert await _preview(fts_db, "We run AI jobs nightly", "ai") == "We run <mark>AI</mark> jobs nightly"


@pytest.mark.asyncio
async def test_every_occurrence_inside_the_window_is_marked(fts_db: AsyncSession) -> None:
    preview = await _preview(fts_db, "ci runs, then ci passes", "ci")

    assert preview == "<mark>ci</mark> runs, then <mark>ci</mark> passes"


@pytest.mark.asyncio
async def test_the_search_dialog_escapes_the_message_around_the_marked_match(fts_db: AsyncSession) -> None:
    await seed_chat_with_text(fts_db, "chat-html", "<b onmouseover=x>部署</b>", "ok")

    items, _total = await ChatService.search_messages("部署", limit=10)

    assert [item["snippet"] for item in items] == ["&lt;b onmouseover=x&gt;<mark>部署</mark>&lt;/b&gt;"]


def test_a_match_longer_than_the_window_is_shown_whole() -> None:
    needle = "slowly rolling out the new sandbox build to every region we host"
    assert len(needle) > _WINDOW

    assert ChatMessageSearchRepository.substring_snippet(f"{_BEFORE}{needle}{_AFTER}", needle) == f"...<mark>{needle}</mark>..."


def test_a_needle_the_text_does_not_hold_previews_the_head_unmarked() -> None:
    content = "abcdef" * 20

    assert ChatMessageSearchRepository.substring_snippet(content, "zzz") == f"{content[:_WINDOW]}..."


@pytest.mark.parametrize("needle", ["部署流", "部署流程", "部署流程图片"])
@pytest.mark.parametrize("position", ["start", "middle", "end"])
@pytest.mark.asyncio
async def test_a_lone_match_at_the_start_middle_or_end_is_cut_like_the_trigram_window(
    fts_db: AsyncSession, needle: str, position: str
) -> None:
    content = {"start": f"{needle}{_AFTER}", "middle": f"{_BEFORE}{needle}{_AFTER}", "end": f"{_BEFORE}{needle}"}[position]
    await seed_chat_with_text(fts_db, "chat-window", content, "ok")

    rows, _total = await ChatMessageSearchRepository.search_messages_fts(
        fts_db, sanitize_fts5_query(needle), 50, 0, None, None, raw_query=needle
    )

    assert rows[0]["highlight_snippet"] == ChatMessageSearchRepository.substring_snippet(content, needle)
