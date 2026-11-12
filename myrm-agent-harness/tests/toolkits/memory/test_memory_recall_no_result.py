"""The zero-hit reply: a search that covers rules says how rules are matched, on the MCP surface too.

Stored rules are matched as one exact phrase against their trigger and action, so a natural-language query finds
none of them. A client that is only told "nothing found" concludes the rule does not exist and saves a duplicate.

[INPUT]
- toolkits.memory.agent_surface.memory_recall_no_result::no_result_reply (POS: the zero-hit reply both surfaces share)
- toolkits.memory.agent_surface.mcp_server::MemoryMCPServer (POS: MCP adapter exposing memory_recall)
- toolkits.memory.agent_surface.memory_recall_budget::DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT (POS: the recall limits the reply quotes)

[POS]
Reply guard for the shared zero-hit reply; the agent tool's side is covered by test_memory_search_zero_hit_reply.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_budget import DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_no_result import no_result_reply
from myrm_agent_harness.toolkits.memory.types import MemoryType

_PLAIN = "No relevant memories found."


async def _recall(*, categories: list[str] | None, degraded: bool = False) -> str:
    manager = AsyncMock()
    manager.search = AsyncMock(return_value=[])
    manager.last_retrieval_trace = SimpleNamespace(degraded=degraded)
    arguments: dict[str, object] = {"query": "summarize code changes in one sentence"}
    if categories is not None:
        arguments["categories"] = categories
    result = await MemoryMCPServer(manager, server_name="test-memory").mcp.call_tool("memory_recall", arguments)
    return "".join(str(getattr(block, "text", "")) for block in getattr(result, "content", []))


@pytest.mark.parametrize(
    "categories",
    [None, ["rule"], ["instruction"], ["knowledge", "rule"], ["no-such-category"]],
    ids=["all", "rule", "instruction", "knowledge-and-rule", "unknown-category-searches-all"],
)
async def test_a_recall_that_covers_rules_says_how_rules_are_matched(categories: list[str] | None) -> None:
    reply = await _recall(categories=categories)

    assert reply.startswith(f"{_PLAIN} Stored rules are matched as one exact phrase against their trigger and action")
    assert 'categories=["rule"]' in reply
    assert f"({DEFAULT_RECALL_LIMIT} per call, up to {MAX_RECALL_LIMIT} with limit)" in reply


@pytest.mark.parametrize(
    "categories",
    [["knowledge"], ["claim"], ["event"], ["preference"], ["knowledge", "event"]],
    ids=["knowledge", "claim", "event", "preference", "knowledge-and-event"],
)
async def test_a_recall_that_leaves_rules_out_gets_the_plain_reply(categories: list[str]) -> None:
    assert await _recall(categories=categories) == _PLAIN


async def test_a_timed_out_recall_is_reported_as_a_timeout_not_as_an_empty_one() -> None:
    reply = await _recall(categories=None, degraded=True)

    assert reply == "Memory search timed out. Try a more specific query or retry."


def test_the_reply_depends_only_on_whether_rules_are_in_scope() -> None:
    covering = no_result_reply(None)

    assert covering != _PLAIN
    assert no_result_reply([MemoryType.PROCEDURAL]) == covering
    assert no_result_reply((MemoryType.SEMANTIC, MemoryType.PROCEDURAL)) == covering
    assert no_result_reply([MemoryType.SEMANTIC]) == _PLAIN
    assert no_result_reply((MemoryType.EPISODIC, MemoryType.CLAIM)) == _PLAIN
