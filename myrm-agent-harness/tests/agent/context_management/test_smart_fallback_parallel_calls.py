"""Parallel tool calls share one AIMessage; smart fallback keeps it once and charges it once.

A budget that holds the whole conversation, with each shared AIMessage counted once, must therefore hold every result
of every batch. When the budget runs short it is the oldest results of a batch that go.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.strategies.compactor.smart_fallback import apply_smart_fallback
from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

_SLACK_TOKENS = 20


def _batch(batch: int, calls: int) -> list[BaseMessage]:
    """One AIMessage announcing ``calls`` parallel calls, followed by their results."""
    ids = [f"b{batch}c{index}" for index in range(calls)]
    announce = AIMessage(
        content="reading all modules",
        tool_calls=[{"id": call_id, "name": "read_file", "args": {"path": f"{call_id}.py"}} for call_id in ids],
    )
    results = [ToolMessage(content="alpha beta gamma delta " * 8, tool_call_id=call_id) for call_id in ids]
    return [announce, *results]


def _result_ids(messages: list[BaseMessage]) -> list[str]:
    return [m.tool_call_id for m in messages if isinstance(m, ToolMessage)]


def _announcements(messages: list[BaseMessage]) -> list[list[str]]:
    return [[str(call["id"]) for call in m.tool_calls] for m in messages if isinstance(m, AIMessage)]


async def test_a_budget_that_holds_the_conversation_keeps_every_result_of_a_parallel_batch() -> None:
    original = [HumanMessage(content="go"), *_batch(0, calls=12)]

    result, _ = await apply_smart_fallback(original, max_tokens=estimate_messages_tokens(original) + _SLACK_TOKENS)

    assert _result_ids(result) == [f"b0c{index}" for index in range(12)]
    assert len(_announcements(result)) == 1


async def test_a_short_budget_drops_the_oldest_results_of_a_parallel_batch() -> None:
    original = [HumanMessage(content="go"), *_batch(0, calls=12)]
    result_tokens = estimate_messages_tokens(original[-1:])
    budget = estimate_messages_tokens(original[:2]) + 4 * result_tokens + result_tokens // 2

    result, _ = await apply_smart_fallback(original, max_tokens=budget)

    newest_four = [f"b0c{index}" for index in range(8, 12)]
    assert _result_ids(result) == newest_four
    assert _announcements(result) == [newest_four]


async def test_every_batch_keeps_its_own_announcement() -> None:
    original = [HumanMessage(content="go"), *_batch(0, calls=3), HumanMessage(content="more"), *_batch(1, calls=3)]

    result, _ = await apply_smart_fallback(original, max_tokens=estimate_messages_tokens(original) + _SLACK_TOKENS)

    assert _announcements(result) == [["b0c0", "b0c1", "b0c2"], ["b1c0", "b1c1", "b1c2"]]
    assert len(_result_ids(result)) == 6
