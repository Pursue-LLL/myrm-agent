"""Smart fallback keeps the newest tool-call groups and returns the conversation in its original order.

The groups share one token budget and are filled from the newest backwards, so when the budget runs out it is the
oldest groups that go. Whatever is kept is put back in conversation order, and no tool result is left without the call
that announced it.
"""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.strategies.compactor.smart_fallback import apply_smart_fallback
from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

_MARKER = re.compile(r"\b[qa]\d+\b")


def _body(tag: str, words: int) -> str:
    return f"{tag}: " + "alpha beta gamma delta " * words


def _group(index: int, words: int) -> list[BaseMessage]:
    call = {"id": f"c{index}", "name": "shell", "args": {"cmd": f"step-{index}"}}
    return [
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(content=_body(f"result {index}", words), name="shell", tool_call_id=f"c{index}"),
    ]


def _two_turns(groups_per_turn: int, words: int) -> list[BaseMessage]:
    """Two question/answer turns, each with its own tool calls; every plain message carries a ``q``/``a`` marker."""
    messages: list[BaseMessage] = [HumanMessage(content="q1 first question")]
    for index in range(groups_per_turn):
        messages += _group(index, words)
    messages += [AIMessage(content="a1 first answer"), HumanMessage(content="q2 second question")]
    for index in range(groups_per_turn, 2 * groups_per_turn):
        messages += _group(index, words)
    messages.append(AIMessage(content="a2 second answer"))
    return messages


def _marker(message: BaseMessage) -> str:
    """The original message an output message stands for: its call id, or the marker its text carries."""
    if isinstance(message, ToolMessage):
        return message.tool_call_id
    if isinstance(message, AIMessage) and message.tool_calls:
        return str(message.tool_calls[0]["id"])
    found = _MARKER.search(str(message.content))
    assert found is not None, f"no marker in {message.content!r}"
    return found.group()


def _original_order(messages: list[BaseMessage]) -> dict[str, int]:
    return {_marker(message): index for index, message in enumerate(messages)}


def _kept_call_numbers(messages: list[BaseMessage]) -> list[int]:
    return sorted(int(m.tool_call_id[1:]) for m in messages if isinstance(m, ToolMessage))


def _plain_tokens(messages: list[BaseMessage]) -> int:
    """Tokens of the messages that are not part of a tool-call group."""
    plain = [m for m in messages if not isinstance(m, ToolMessage) and not (isinstance(m, AIMessage) and m.tool_calls)]
    return estimate_messages_tokens(plain)


async def test_the_kept_messages_come_back_in_their_original_order() -> None:
    original = _two_turns(groups_per_turn=3, words=50)
    order = _original_order(original)

    result, _ = await apply_smart_fallback(original, max_tokens=estimate_messages_tokens(original) * 2)

    positions = [order[_marker(message)] for message in result]
    assert positions == sorted(positions)


async def test_a_tight_budget_keeps_the_newest_groups_and_drops_the_oldest() -> None:
    original = _two_turns(groups_per_turn=7, words=225)

    result, _ = await apply_smart_fallback(original, max_tokens=_plain_tokens(original) + 2_000)

    kept = _kept_call_numbers(result)
    assert 0 < len(kept) < 14
    assert kept == list(range(kept[0], 14))


async def test_no_tool_result_is_left_without_the_call_that_announced_it() -> None:
    original = _two_turns(groups_per_turn=7, words=225)

    result, _ = await apply_smart_fallback(original, max_tokens=_plain_tokens(original) + 2_000)

    announced: set[str] = set()
    for message in result:
        if isinstance(message, AIMessage):
            announced.update(str(call["id"]) for call in message.tool_calls)
        if isinstance(message, ToolMessage):
            assert message.tool_call_id in announced


async def test_a_parallel_call_keeps_each_tool_call_announced_once() -> None:
    calls = [{"id": f"p{i}", "name": "shell", "args": {"cmd": str(i)}} for i in range(3)]
    original: list[BaseMessage] = [
        HumanMessage(content="q1 question"),
        AIMessage(content="", tool_calls=calls),
        *(ToolMessage(content=_body(f"p{i}", 100), name="shell", tool_call_id=f"p{i}") for i in range(3)),
        AIMessage(content="a1 answer"),
    ]

    result, _ = await apply_smart_fallback(original, max_tokens=estimate_messages_tokens(original) * 2)

    announced = [str(call["id"]) for m in result if isinstance(m, AIMessage) for call in m.tool_calls]
    assert len(announced) == len(set(announced))
    assert set(announced) == {m.tool_call_id for m in result if isinstance(m, ToolMessage)}
