"""A memory search that finds nothing says how rules are matched and which time window ran.

Stored rules are matched as one exact phrase against their trigger and action, so a natural-language query finds
none of them. A model that is only told "nothing found" concludes the rule does not exist and saves a duplicate of it.
since/until match when a memory was saved, so a memory saved outside an explicit window is invisible to the search;
a model that is not told the window concludes the memory does not exist.

[INPUT]
- toolkits.memory.agent_surface.memory_search_execution::search_memory_corpus (POS: memory corpus search of memory_search_tool)
- toolkits.memory.agent_surface.memory_agent_tools.common::CATEGORY_TO_TYPE (POS: agent-visible category names)
- toolkits.memory.agent_surface.memory_recall_budget::DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT (POS: the recall limits the reply quotes)
- toolkits.memory.setup::create_local_memory_manager (POS: embeddings-less local memory manager)

[POS]
Reply guard for a memory search that returns nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.common import CATEGORY_TO_TYPE
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_budget import DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution import search_memory_corpus
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryType, SemanticMemory

_PLAIN = "No relevant memories found."
_MARCH_WINDOW_NOTE = (
    f"{_PLAIN} This search was limited to memories saved after 2026-03-01 00:00 UTC and before 2026-03-31 00:00 UTC: "
    "since/until match when a memory was saved, not the date it describes. "
    "If the memory may have been saved outside this period, retry without since/until."
)


async def _search(
    results: list[MemorySearchResult],
    *,
    categories: list[str] | None,
    domain: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> str:
    manager = AsyncMock()
    manager.search = AsyncMock(return_value=results)
    manager.active_session = None
    manager.last_retrieval_trace = None
    manager.set_last_cited_memory_ids = MagicMock()
    with patch(
        "myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution.emit_cited_memory_ids", AsyncMock()
    ):
        return await search_memory_corpus(
            manager,
            query="summarize code changes in one sentence",
            category_to_type=CATEGORY_TO_TYPE,
            categories=categories,
            limit=None,
            since=since,
            until=until,
            domain=domain,
        )


@pytest.mark.parametrize(
    "categories",
    [None, ["rule"], ["instruction"], ["knowledge", "rule"], ["no-such-category"]],
    ids=["all", "rule", "instruction", "knowledge-and-rule", "unknown-category-searches-all"],
)
async def test_a_search_that_covers_rules_says_how_rules_are_matched(categories: list[str] | None) -> None:
    reply = await _search([], categories=categories)

    assert reply.startswith(f"{_PLAIN} Stored rules are matched as one exact phrase against their trigger and action")
    assert 'categories=["rule"]' in reply
    assert f"({DEFAULT_RECALL_LIMIT} per call, up to {MAX_RECALL_LIMIT} with limit)" in reply


@pytest.mark.parametrize(
    "categories",
    [["knowledge"], ["event"], ["preference"], ["knowledge", "event"]],
    ids=["knowledge", "event", "preference", "knowledge-and-event"],
)
async def test_a_search_that_leaves_rules_out_gets_the_plain_reply(categories: list[str]) -> None:
    assert await _search([], categories=categories) == _PLAIN


async def test_a_search_whose_every_hit_is_filtered_out_gets_the_same_reply() -> None:
    hit = MemorySearchResult(
        memory=SemanticMemory(content="User prefers dark mode"), memory_type=MemoryType.SEMANTIC, score=0.9
    )

    assert await _search([hit], categories=["knowledge"], domain="finance") == _PLAIN
    assert (await _search([hit], categories=None, domain="finance")).startswith(f"{_PLAIN} Stored rules")


async def test_a_search_under_an_explicit_window_names_it() -> None:
    reply = await _search([], categories=["knowledge"], since="2026-03-01", until="2026-03-31")

    assert reply == _MARCH_WINDOW_NOTE


async def test_a_search_whose_every_hit_is_filtered_out_names_the_window_too() -> None:
    hit = MemorySearchResult(
        memory=SemanticMemory(content="User prefers dark mode"), memory_type=MemoryType.SEMANTIC, score=0.9
    )

    reply = await _search([hit], categories=["knowledge"], domain="finance", since="2026-03-01", until="2026-03-31")

    assert reply == _MARCH_WINDOW_NOTE


async def test_a_search_over_rules_only_does_not_blame_a_window_it_never_read() -> None:
    reply = await _search([], categories=["rule"], since="2026-03-01", until="2026-03-31")

    assert reply == await _search([], categories=["rule"])


@pytest.mark.slow
@pytest.mark.asyncio
async def test_a_memory_saved_before_the_window_is_only_found_without_it(tmp_path: Path) -> None:
    saved = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
    manager = await create_local_memory_manager(tmp_path / "mem", None)
    try:
        await manager.store(
            SemanticMemory(
                id=str(uuid4()),
                user_id="sandbox_user",
                content="User prefers dark mode in every editor and terminal",
                created_at=saved,
                updated_at=saved,
            )
        )

        async def search(*, since: str | None, until: str | None) -> str:
            return await search_memory_corpus(
                manager,
                query="dark mode editor terminal",
                category_to_type=CATEGORY_TO_TYPE,
                categories=["knowledge"],
                limit=5,
                since=since,
                until=until,
            )

        windowed = await search(since="2026-03-01", until="2026-03-31")
        unwindowed = await search(since=None, until=None)
    finally:
        await manager.close()

    assert windowed == _MARCH_WINDOW_NOTE
    assert "User prefers dark mode in every editor and terminal" in unwindowed
