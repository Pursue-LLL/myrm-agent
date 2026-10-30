"""How the shipped agent runs the tool calls of one model turn, observed on the graph a run builds.

The tool calls of a turn reach the tool node as separate tasks that start in no fixed order, so what a test can pin is
what holds in every order: which calls may run at the same moment, which never do, and that a paused call neither
stalls nor re-runs its siblings. Each test here compiles the stack ``build_middlewares`` assembles with
``create_agent``, as ``test_shipped_stack_hooks`` does, and reads what the tools saw.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import ToolException, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from myrm_agent_harness.agent.middlewares.tooling import tool_executor
from myrm_agent_harness.agent.security.tool_registry import TOOL_SAFETY_METADATA, SafetyMetadata
from tests.support.shipped_graph import shipped_agent, shipped_session

HOLD_SECONDS = 0.15
# Two slow calls one after the other take longer than SLOW_TOOL_TIMEOUT, each one alone takes less; the margins are
# wide so that a busy machine does not tip a call over its timeout.
SLOW_HOLD_SECONDS = 0.6
SLOW_TOOL_TIMEOUT = 0.9


class Probe:
    """Which tool calls are executing at the same moment, and which ones have finished."""

    def __init__(self) -> None:
        self.running: list[str] = []
        self.together: list[frozenset[str]] = []
        self.finished: list[str] = []
        self.ran: list[str] = []
        self.received: dict[str, object] = {}

    async def hold(self, name: str, seconds: float = HOLD_SECONDS) -> None:
        self.running.append(name)
        if len(self.running) > 1:
            self.together.append(frozenset(self.running))
        try:
            await asyncio.sleep(seconds)
        finally:
            self.running.remove(name)
            self.finished.append(name)

    def overlapped(self, first: str, second: str) -> bool:
        return any({first, second} <= moment for moment in self.together)


PROBE = Probe()


@tool
async def read_one(tag: str) -> str:
    """Read the first source."""
    await PROBE.hold("read_one")
    return "read one"


@tool
async def read_two(tag: str) -> str:
    """Read the second source."""
    await PROBE.hold("read_two")
    return "read two"


@tool
async def write_one(tag: str) -> str:
    """Change the first target."""
    await PROBE.hold("write_one")
    return "wrote one"


@tool
async def write_two(tag: str) -> str:
    """Change the second target."""
    await PROBE.hold("write_two")
    return "wrote two"


@tool
async def slow_write_one(tag: str) -> str:
    """Change the first target slowly."""
    await PROBE.hold("slow_write_one", SLOW_HOLD_SECONDS)
    return "slowly wrote one"


@tool
async def slow_write_two(tag: str) -> str:
    """Change the second target slowly."""
    await PROBE.hold("slow_write_two", SLOW_HOLD_SECONDS)
    return "slowly wrote two"


@tool
async def write_after_asking(tag: str) -> str:
    """Change a target once the user agreed."""
    answer = interrupt({"question": "go ahead?"})
    await PROBE.hold("write_after_asking")
    return f"wrote after {answer}"


@tool
async def fail_one(tag: str) -> str:
    """Change the first target, which fails."""
    PROBE.ran.append("fail_one")
    raise ToolException("fail_one failed")


@tool
async def fail_two(tag: str) -> str:
    """Change the second target, which fails."""
    PROBE.ran.append("fail_two")
    raise ToolException("fail_two failed")


fail_one.handle_tool_error = True
fail_two.handle_tool_error = True


@tool
async def collect(items: list[str], tag: str) -> str:
    """Join the items."""
    PROBE.received["items"] = items
    return ",".join(items)


@tool
async def filter_rows(filters: dict[str, str], tag: str) -> str:
    """Select the rows matching the filters."""
    PROBE.received["filters"] = filters
    return "selected"


TOOLS = [
    read_one,
    read_two,
    write_one,
    write_two,
    slow_write_one,
    slow_write_two,
    write_after_asking,
    fail_one,
    fail_two,
    collect,
    filter_rows,
]
READERS = {"read_one", "read_two"}
WRITERS = {"write_one", "write_two", "slow_write_one", "slow_write_two", "write_after_asking", "fail_one", "fail_two"}


@pytest.fixture(autouse=True)
def _session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    global PROBE
    PROBE = Probe()
    for name in READERS:
        monkeypatch.setitem(TOOL_SAFETY_METADATA, name, SafetyMetadata(is_read_only=True, is_concurrent_safe=True))
    for name in WRITERS:
        monkeypatch.setitem(TOOL_SAFETY_METADATA, name, SafetyMetadata(is_destructive=True))
    with shipped_session(tmp_path):
        yield


def _turn(tag: str, **calls: dict[str, object]) -> AIMessage:
    """One model turn that makes every call at once; *calls* maps a tool name to its arguments."""
    return AIMessage(
        content="",
        tool_calls=[
            {"id": f"{name}-{tag}", "name": name, "args": {"tag": tag, **args}} for name, args in calls.items()
        ],
    )


async def _run(tag: str, **calls: dict[str, object]) -> list[ToolMessage]:
    _, agent = shipped_agent([_turn(tag, **calls), AIMessage(content="done")], TOOLS)
    result = await agent.ainvoke({"messages": [HumanMessage(content="go")]})
    return [m for m in result["messages"] if isinstance(m, ToolMessage)]


async def test_read_only_calls_of_one_turn_run_at_the_same_time() -> None:
    answers = await _run("readers", read_one={}, read_two={})

    assert sorted(m.content for m in answers) == ["read one", "read two"]
    assert PROBE.overlapped("read_one", "read_two")


async def test_mutating_calls_of_one_turn_never_run_at_the_same_time() -> None:
    answers = await _run("writers", write_one={}, write_two={})

    assert sorted(m.content for m in answers) == ["wrote one", "wrote two"]
    assert PROBE.together == []


async def test_a_mutating_call_never_runs_while_a_read_only_call_of_the_same_turn_does() -> None:
    answers = await _run("mixed", read_one={}, write_one={}, read_two={})

    assert sorted(m.content for m in answers) == ["read one", "read two", "wrote one"]
    assert not PROBE.overlapped("write_one", "read_one")
    assert not PROBE.overlapped("write_one", "read_two")


async def test_a_call_waiting_for_another_does_not_spend_its_timeout_waiting_and_is_not_run_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tool_executor, "get_tool_timeout", lambda name, args: SLOW_TOOL_TIMEOUT)

    answers = await _run("slow", slow_write_one={}, slow_write_two={})

    assert [m.status for m in answers] == ["success", "success"]
    assert sorted(PROBE.finished) == ["slow_write_one", "slow_write_two"]


async def test_when_a_mutating_call_fails_the_turns_other_mutating_call_is_skipped_not_run() -> None:
    answers = await _run("failing", fail_one={}, fail_two={})

    assert len(PROBE.ran) == 1
    assert sorted(m.status for m in answers) == ["error", "error"]
    assert sorted("[SKIPPED]" in str(m.content) for m in answers) == [False, True]


async def test_a_list_argument_sent_as_a_json_string_reaches_the_tool_as_a_list() -> None:
    answers = await _run("whole", collect={"items": '["a", "b"]'})

    assert PROBE.received["items"] == ["a", "b"]
    assert [m.content for m in answers] == ["a,b"]


async def test_an_object_argument_cut_off_mid_string_is_repaired_before_the_tool_sees_it() -> None:
    await _run("cut", filter_rows={"filters": '{"status": "open", "kind": "fil'})

    assert PROBE.received["filters"] == {"status": "open", "kind": "fil"}


async def test_a_json_string_that_cannot_be_repaired_is_answered_as_an_error_and_the_run_goes_on() -> None:
    answers = await _run("broken", filter_rows={"filters": '{"status": '})

    assert "filters" not in PROBE.received
    assert [m.status for m in answers] == ["error"]


@pytest.mark.parametrize("attempt", range(6))
async def test_a_call_that_pauses_for_the_user_neither_stalls_its_sibling_nor_re_runs_it(attempt: int) -> None:
    """The calls start in a different order from one run to the next, so the pause lands before or after the sibling."""
    tag = f"pause{attempt}"
    _, agent = shipped_agent(
        [_turn(tag, write_after_asking={}, write_two={}), AIMessage(content="done")],
        TOOLS,
        checkpointer=InMemorySaver(),
    )
    thread = {"configurable": {"thread_id": tag}}

    paused = await asyncio.wait_for(agent.ainvoke({"messages": [HumanMessage(content="go")]}, thread), timeout=10)
    assert paused["__interrupt__"]
    assert PROBE.finished == ["write_two"]

    resumed = await asyncio.wait_for(agent.ainvoke(Command(resume="yes"), thread), timeout=10)

    answers = [m.content for m in resumed["messages"] if isinstance(m, ToolMessage)]
    assert sorted(answers) == ["wrote after yes", "wrote two"]
    assert sorted(PROBE.finished) == ["write_after_asking", "write_two"]
