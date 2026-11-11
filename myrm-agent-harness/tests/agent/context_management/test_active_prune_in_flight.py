"""ActiveToolResultPruneProcessor shows the turn's earlier results as its first signed reasoning block saw them.

A signed block is bound to every message before it, so replacing an earlier tool result while a block written after it
is still to be replayed would make the provider refuse that block. From the first signed block of a turn on, the
processor decides over the messages before it, the list the request that wrote the block was given: what was pruned
then is pruned again, exactly as it was, and what falls out of the recent window during the turn waits for the next
one. Nothing is kept in memory for this, so a pipeline built for a resume after an approval reaches the same view. A
prune the runtime forces to make room is not held back.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.active_tool_result_prune_processor import (
    ActiveToolResultPruneProcessor,
)
from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY

_BLOCKS = [{"type": "thinking", "thinking": "plan", "signature": "sig"}]
_RECENT = 2
_THRESHOLD = 256


async def _offload(*, content: str, tool_name: str, scope_id: str | None) -> str:
    return f"/archive/{tool_name}/{hashlib.sha256(content.encode()).hexdigest()[:8]}.txt"


def _round(number: int, *, signed: bool) -> list[BaseMessage]:
    """One tool round: a call (led by a signed block when ``signed``) and its result, large enough to be pruned."""
    kwargs = {THINKING_BLOCKS_KEY: _BLOCKS} if signed else {}
    call = {"id": f"c{number}", "name": "grep_tool", "args": {}}
    result = f"result {number}: " + "alpha beta gamma delta " * 400
    return [
        AIMessage(content="", tool_calls=[call], additional_kwargs=kwargs),
        ToolMessage(content=result, name="grep_tool", tool_call_id=f"c{number}"),
    ]


def _rounds(first: int, last: int, *, signed: bool) -> list[BaseMessage]:
    return [message for number in range(first, last + 1) for message in _round(number, signed=signed)]


def _results(messages: Sequence[BaseMessage]) -> dict[str, str]:
    """What each tool call's result reads as, by call id."""
    return {m.tool_call_id: str(m.content) for m in messages if isinstance(m, ToolMessage)}


def _processor() -> ActiveToolResultPruneProcessor:
    return ActiveToolResultPruneProcessor(
        threshold_tokens=_THRESHOLD, keep_recent_calls=_RECENT, on_prune_offload=_offload
    )


def _context(messages: list[BaseMessage], **metadata: object) -> ProcessorContext:
    return ProcessorContext(messages=messages, user_query="go", chat_id="chat", metadata=dict(metadata))


async def _view(messages: list[BaseMessage]) -> dict[str, str]:
    """What a request over ``messages`` shows, in a pipeline built just for it."""
    return _results((await _processor().process(_context(messages))).messages)


async def test_a_turn_in_flight_prunes_nothing_of_its_own() -> None:
    messages = [HumanMessage(content="go"), *_rounds(1, 5, signed=True)]

    result = await _processor().process(_context(messages))

    assert _results(result.messages) == _results(messages)
    assert result.tokens_saved == 0


async def test_without_signed_blocks_every_result_behind_the_recent_ones_is_pruned() -> None:
    messages = [HumanMessage(content="go"), *_rounds(1, 5, signed=False)]
    original = _results(messages)

    shown = await _view(messages)

    assert [shown[f"c{n}"] != original[f"c{n}"] for n in range(1, 6)] == [True, True, True, False, False]
    assert "/archive/grep_tool/" in shown["c1"]


async def test_what_the_turn_began_with_stays_pruned_and_nothing_else_joins_it() -> None:
    history = [HumanMessage(content="go"), *_rounds(1, 5, signed=False)]
    began_with = await _view([*history, HumanMessage(content="more")])

    state = [*history, HumanMessage(content="more"), *_rounds(6, 8, signed=True)]
    shown = await _view(state)
    original = _results(state)

    assert [shown[f"c{n}"] for n in (1, 2, 3)] == [began_with[f"c{n}"] for n in (1, 2, 3)]
    assert all(shown[f"c{n}"] != original[f"c{n}"] for n in (1, 2, 3))
    assert all(shown[f"c{n}"] == original[f"c{n}"] for n in range(4, 9))


async def test_the_first_signed_block_fixes_the_view_even_when_the_turn_ran_unsigned_before_it() -> None:
    # A model that decides when to think can answer the first rounds of a turn without a block.
    unsigned = [HumanMessage(content="go"), *_rounds(1, 4, signed=False)]
    when_it_was_written = await _view(unsigned)

    state = [*unsigned, *_rounds(5, 7, signed=True)]
    shown = await _view(state)
    original = _results(state)

    assert [shown[f"c{n}"] for n in range(1, 5)] == [when_it_was_written[f"c{n}"] for n in range(1, 5)]
    assert [shown[f"c{n}"] != original[f"c{n}"] for n in range(1, 5)] == [True, True, False, False]
    assert all(shown[f"c{n}"] == original[f"c{n}"] for n in range(5, 8))


@pytest.mark.parametrize("pause", ["resume after an approval", "human session in progress"])
async def test_a_resume_in_a_new_pipeline_shows_what_the_turn_showed_before_the_pause(pause: str) -> None:
    history = [HumanMessage(content="go"), *_rounds(1, 5, signed=False)]
    began_with = await _view([*history, HumanMessage(content="more")])

    state = [*history, HumanMessage(content="more"), *_rounds(6, 8, signed=True)]
    resumed = _context(state)
    if pause == "resume after an approval":
        resumed.is_resume = True
    else:
        resumed.merged_context["hitl_session_active"] = True
    processor = _processor()
    assert await processor.should_process(resumed)
    shown = _results((await processor.process(resumed)).messages)
    original = _results(state)

    assert [shown[f"c{n}"] for n in (1, 2, 3)] == [began_with[f"c{n}"] for n in (1, 2, 3)]
    assert all(shown[f"c{n}"] == original[f"c{n}"] for n in range(4, 9))


async def test_a_resume_of_a_route_that_signs_nothing_leaves_the_prompt_alone() -> None:
    state = [HumanMessage(content="go"), *_rounds(1, 5, signed=False)]
    resumed = _context(state)
    resumed.is_resume = True

    assert not await _processor().should_process(resumed)


async def test_a_prune_the_runtime_forces_runs_even_in_flight() -> None:
    messages = [HumanMessage(content="go"), *_rounds(1, 5, signed=True)]
    original = _results(messages)

    result = await _processor().process(_context(messages, force_prune=True))
    shown = _results(result.messages)

    assert [shown[f"c{n}"] != original[f"c{n}"] for n in range(1, 6)] == [True, True, True, False, False]
