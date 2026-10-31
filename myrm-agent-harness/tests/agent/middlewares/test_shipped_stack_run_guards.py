"""Whether the guards a run counts with are one object from one tool call to the next, observed on the shipped graph.

The call-frequency window, the per-turn tool budget and the context budget each count across the tool calls of a run,
so each has to be the same object for the whole run. They are created on first use inside a tool call, and LangGraph
runs a tool call in a copy of the context that is dropped afterwards, so a guard created there is not seen by the next
call. The helpers a nested run uses (``isolated_run_guards``) put a guard into the context before the run starts; the
run of a user does not, and ``reset_all_guards`` only resets a guard that is already there.

The run below starts from an empty context, like the context a run starts in, so that a guard an earlier test left in
the process cannot make it look better than it is.
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Callable
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from myrm_agent_harness.agent.middlewares.tooling import _tool_guards
from myrm_agent_harness.agent.security.tool_registry import TOOL_SAFETY_METADATA, SafetyMetadata
from tests.support.shipped_graph import shipped_agent, shipped_session

GUARD_GETTERS = ("get_frequency_guard", "get_tool_turn_budget_guard", "get_context_budget_guard")
TURNS = 2
CALLS_PER_TURN = 15
# Every round of the shipped graph costs about a dozen steps, so the default limit would end the run first.
RECURSION_LIMIT = 100


@tool
async def read_source(tag: str) -> str:
    """Read one source."""
    # The text differs per call: the same answer to every call would be stopped by the loop guard instead.
    return f"source {tag} " + "x" * (int(tag) * 7)


def _turn(first: int) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"id": f"call-{number}", "name": "read_source", "args": {"tag": str(number)}}
            for number in range(first, first + CALLS_PER_TURN)
        ],
    )


def _recording(fetch: Callable[[], object], into: list[object]) -> Callable[[], object]:
    def getter() -> object:
        guard = fetch()
        # The guard itself, not its id: an id can be handed to the next guard once this one is collected.
        into.append(guard)
        return guard

    return getter


def _guards_got_by_a_run(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> dict[str, list[object]]:
    """The guard each tool call of a two-turn run was given, by the name of the getter."""
    got: dict[str, list[object]] = {name: [] for name in GUARD_GETTERS}
    for name in GUARD_GETTERS:
        monkeypatch.setattr(_tool_guards, name, _recording(getattr(_tool_guards, name), got[name]))
    monkeypatch.setitem(TOOL_SAFETY_METADATA, "read_source", SafetyMetadata(is_read_only=True, is_concurrent_safe=True))
    script = [_turn(0), _turn(CALLS_PER_TURN), AIMessage(content="done")]
    _, agent = shipped_agent(script, [read_source])

    async def run() -> None:
        with shipped_session(workspace, own_frequency_window=False):
            await agent.ainvoke({"messages": [HumanMessage(content="go")]}, {"recursion_limit": RECURSION_LIMIT})

    contextvars.Context().run(asyncio.run, run())
    return got


def test_every_tool_call_asks_for_each_of_the_three_guards(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    got = _guards_got_by_a_run(monkeypatch, tmp_path)

    assert {name: len(guards) >= TURNS * CALLS_PER_TURN for name, guards in got.items()} == dict.fromkeys(
        GUARD_GETTERS, True
    )


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="A run installs none of the three guards, so each tool call counts against a new, empty one and no limit is "
    "ever reached. Remove this marker when a run installs them.",
)
def test_each_guard_is_one_object_for_the_whole_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    got = _guards_got_by_a_run(monkeypatch, tmp_path)

    distinct = {name: len({id(guard) for guard in guards}) for name, guards in got.items()}
    assert distinct == dict.fromkeys(GUARD_GETTERS, 1)
