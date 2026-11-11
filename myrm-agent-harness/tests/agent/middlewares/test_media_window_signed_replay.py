"""A loop of screenshots keeps what each signed reasoning block was written under, until the turn ends.

A block the provider signed is bound to every message before it, the images of earlier tool results included. The
media window keeps the newest two media messages of the history, so one more screenshot would rewrite an earlier
message and the provider would refuse every block written before it. These cases run the whole shipped stack against
a provider double that enforces that binding.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic, RequestRecord (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.signed_tool_loop::signed_agent, run_signed_loop, signed_loop_session (POS: turns of the shipped agent in a tool loop against that double)
- tests.support.virtual_clock::virtual_clock, start_run (POS: an idle gap without the wait)

[POS]
Graph-level guard of the media window on a route that signs reasoning: a turn in flight keeps its media up to the
count a provider takes, the next turn retires what the window leaves behind and keeps it retired, and a route that
signs nothing keeps the plain window.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from tests.support.enforcing_anthropic import EnforcingAnthropic, RequestRecord
from tests.support.signed_tool_loop import run_signed_loop, signed_agent, signed_loop_session
from tests.support.virtual_clock import start_run, virtual_clock

_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
_STRIPPED = "Media removed"
# The count of images a request may carry on every platform before the provider applies a stricter per-image limit.
_IMAGES_A_REQUEST_MAY_CARRY = 20
_WINDOW = 200_000


def _screenshot(path: str) -> list[dict[str, object]]:
    return [
        {"type": "text", "text": f"screenshot of {path}"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_PNG}"}},
    ]


@tool("read_file")
async def screenshot(path: str) -> list[dict[str, object]]:
    """Take a screenshot."""
    return _screenshot(path)


@tool("read_file")
async def screenshot_after_approval(path: str) -> list[dict[str, object]]:
    """Take a screenshot; the fourth one waits for the user's approval."""
    if path == "/f4.txt":
        interrupt("approve this screenshot?")
    return _screenshot(path)


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    with signed_loop_session(tmp_path):
        yield


def _stripped(records: list[RequestRecord]) -> list[int]:
    """How many images each request shows as removed."""
    return [record.text.count(_STRIPPED) for record in records]


async def test_a_loop_of_screenshots_is_replayed_to_its_last_block() -> None:
    double = EnforcingAnthropic(tool_rounds=6)

    await run_signed_loop(double, tools=[screenshot], turns=1)

    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    assert [record.replayed for record in double.accepted] == list(range(7))
    assert _stripped(double.accepted) == [0] * 7


async def test_past_the_count_a_provider_takes_the_old_screenshots_go_in_one_step() -> None:
    double = EnforcingAnthropic(tool_rounds=24)

    await run_signed_loop(double, tools=[screenshot], turns=1)

    # Request n carries n - 1 screenshots; the one that would carry the 21st is the one the provider refuses.
    held = _IMAGES_A_REQUEST_MAY_CARRY + 1
    assert [record.status for record in double.requests[:held]] == [200] * held
    assert [record.status for record in double.refused] == [400]
    assert double.requests[held].status == 400
    assert _stripped(double.accepted)[-1] > 0


async def test_the_next_turn_retires_what_the_window_leaves_and_it_stays_retired() -> None:
    double = EnforcingAnthropic(tool_rounds=3)

    await run_signed_loop(double, tools=[screenshot], turns=2)

    assert double.refused == []
    # Turn 1 holds all three screenshots; turn 2 opens by retiring the oldest and then holds the rest.
    assert _stripped(double.accepted) == [0, 0, 0, 0, 1, 1, 1, 1]
    assert [record.thinking for record in double.accepted] == [True] * 8


async def test_a_route_that_signs_nothing_keeps_the_plain_window() -> None:
    double = EnforcingAnthropic(tool_rounds=5)

    await run_signed_loop(double, tools=[screenshot], turns=1, reasoning_effort=None)

    assert double.refused == []
    assert not any(record.thinking for record in double.accepted)
    # The newest two media messages stay; every screenshot beyond them is retired as the next one arrives.
    assert _stripped(double.accepted) == [0, 0, 0, 1, 2, 3]


async def test_an_approval_that_takes_ten_minutes_resumes_without_a_refusal() -> None:
    double = EnforcingAnthropic(tool_rounds=6)
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "t"}, "recursion_limit": 400}
    context = {"chat_id": "chat", "max_context_tokens": _WINDOW}

    with double.serving(), virtual_clock() as clock:
        start_run()
        agent = signed_agent(tools=[screenshot_after_approval], checkpointer=saver)
        paused = await agent.ainvoke({"messages": [HumanMessage(content="Investigate.")]}, config, context=context)
        assert paused.get("__interrupt__")
        clock.advance(600.0)
        start_run()
        # The side of a resume that gives the pipeline nothing in memory: a new agent over the same checkpoint.
        resumed_agent = signed_agent(tools=[screenshot_after_approval], checkpointer=saver)
        await resumed_agent.ainvoke(Command(resume="approved"), config, context={**context, "is_resume": True})

    assert double.refused == []
    assert [record.replayed for record in double.accepted] == list(range(7))
    assert all(record.thinking for record in double.accepted)
