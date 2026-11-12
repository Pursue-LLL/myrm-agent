"""A memory search that finds nothing says how rules are matched whenever rules were in scope.

Stored rules are matched as one exact phrase against their trigger and action, so a natural-language query finds
none of them. A model that is only told "nothing found" concludes the rule does not exist and saves a duplicate of it.

[INPUT]
- toolkits.memory.agent_surface.memory_search_execution::search_memory_corpus (POS: memory corpus search of memory_search_tool)
- toolkits.memory.agent_surface.memory_agent_tools.common::CATEGORY_TO_TYPE (POS: agent-visible category names)
- toolkits.memory.agent_surface.memory_recall_budget::DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT (POS: the recall limits the reply quotes)

[POS]
Reply guard for a memory search that returns nothing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.common import CATEGORY_TO_TYPE
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_budget import DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution import search_memory_corpus
from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryType, SemanticMemory

_PLAIN = "No relevant memories found."


async def _search(results: list[MemorySearchResult], *, categories: list[str] | None, domain: str | None = None) -> str:
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
            since=None,
            until=None,
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
