"""What the per-run guards count in the run of a user and in a delegated run, observed on the shipped graph.

The call-frequency window, the per-turn tool budget and the context budget each count across the tool calls of a run,
so each has to be one object for the whole run. They are created on first use inside a tool call, and LangGraph runs a
tool call in a copy of the context that is dropped afterwards, so a guard created there is not seen by the next call.
The run of a user installs none of the three before it starts, so every tool call meets a new, empty guard and none of
their limits is reached. A delegated run installs them first (``isolated_run_guards``), so its limits count.

Both runs start from an empty context, like the context a run starts in, so that a guard an earlier test left in the
process cannot change what they show.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import inspect
from collections.abc import Callable
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from myrm_agent_harness.agent._internals._agent_helpers import isolated_run_guards, reset_all_guards
from myrm_agent_harness.agent.middlewares.tooling import _tool_guards
from myrm_agent_harness.agent.security.guards.frequency_guard import FrequencyGuard
from myrm_agent_harness.agent.security.tool_registry import TOOL_SAFETY_METADATA, SafetyMetadata
from tests.support.shipped_graph import shipped_agent, shipped_session

GUARD_GETTERS = ("get_frequency_guard", "get_tool_turn_budget_guard", "get_context_budget_guard")
TURNS = 2
CALLS_PER_TURN = 15
# Every round of the shipped graph costs about a dozen steps, so the default limit would end the run first.
RECURSION_LIMIT = 100
PER_TOOL_LIMIT = inspect.signature(FrequencyGuard).parameters["per_tool_limit"].default
OVER_THE_LIMIT = 6
FREQUENCY_REFUSAL = "frequency limit exceeded"


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


def _tool_replies_of_a_run(
    monkeypatch: pytest.MonkeyPatch, workspace: Path, *, delegated: bool, calls: int
) -> list[str]:
    """The reply to each of *calls* successive calls of one tool, one call per model turn."""
    monkeypatch.setitem(TOOL_SAFETY_METADATA, "read_source", SafetyMetadata(is_read_only=True, is_concurrent_safe=True))
    turns = [
        AIMessage(content="", tool_calls=[{"id": f"call-{n}", "name": "read_source", "args": {"tag": str(n)}}])
        for n in range(calls)
    ]
    _, agent = shipped_agent([*turns, AIMessage(content="done")], [read_source])

    async def run() -> list[str]:
        with shipped_session(workspace, own_frequency_window=False):
            scope = isolated_run_guards("delegated-run") if delegated else contextlib.nullcontext()
            with scope:
                # What a run does before its first model call (agent_runtime), for the run of a user and a delegated one.
                reset_all_guards()
                state = await agent.ainvoke(
                    {"messages": [HumanMessage(content="go")]}, {"recursion_limit": RECURSION_LIMIT * calls}
                )
        return [str(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]

    return contextvars.Context().run(asyncio.run, run())


def test_the_run_of_a_user_is_not_stopped_by_the_call_frequency_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replies = _tool_replies_of_a_run(monkeypatch, tmp_path, delegated=False, calls=PER_TOOL_LIMIT + OVER_THE_LIMIT)

    assert [reply for reply in replies if FREQUENCY_REFUSAL in reply] == []
    assert len(replies) == PER_TOOL_LIMIT + OVER_THE_LIMIT


def test_a_delegated_run_is_stopped_by_the_call_frequency_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replies = _tool_replies_of_a_run(monkeypatch, tmp_path, delegated=True, calls=PER_TOOL_LIMIT + OVER_THE_LIMIT)

    assert len([reply for reply in replies if FREQUENCY_REFUSAL in reply]) == OVER_THE_LIMIT
    assert len(replies) == PER_TOOL_LIMIT + OVER_THE_LIMIT
