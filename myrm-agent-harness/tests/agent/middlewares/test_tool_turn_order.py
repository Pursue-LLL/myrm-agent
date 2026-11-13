"""Conflicting tool calls of one model message run in the order the model made them, on the graph a run builds.

The calls of one message reach the tool node as separate tasks, so the order in which they reach the conflict gate is
not the model's. Each test forces that arrival order with a middleware in front of the stack, then reads the order in
which the real stack ran the tools. A call conflicts with another when at least one of the two is not
concurrency-safe: ``S`` marks a read-only call, ``E`` a mutating one.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import time
from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from langchain.agents.middleware import AgentMiddleware, AgentState, ToolCallRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares._session_context import set_security_config
from myrm_agent_harness.agent.security.tool_registry import TOOL_SAFETY_METADATA, SafetyMetadata
from myrm_agent_harness.agent.security.types import PrivacyPolicy, SecurityConfig
from tests.support.shipped_graph import shipped_agent, shipped_session

HOLD_SECONDS = 0.05
RENDEZVOUS_SECONDS = 5.0
SETTLE_TURNS = 8
MUTATING_TOOL = "order_write"
READ_ONLY_TOOL = "order_read"
SHAPES = ["EE", "EEEE", "SE", "ES", "SESE", "ESSES", "SSE", "ESS", "SES"]


@dataclass(frozen=True)
class Ran:
    started: float
    finished: float


class Probe:
    """When each tool call ran, and how many ran at the same moment."""

    def __init__(self) -> None:
        self.ran: dict[str, Ran] = {}
        self.running: set[str] = set()
        self.together: list[frozenset[str]] = []
        self.peers = 1
        self._gathered = asyncio.Event()

    async def hold(self, tag: str, *, together_with: int = 1) -> None:
        """Stay running for ``HOLD_SECONDS``, or until *together_with* calls run at once when that is more than one.

        Waiting for the peers instead of for a duration keeps "ran together" independent of the machine's load.
        """
        started = time.monotonic()
        self.running.add(tag)
        if len(self.running) > 1:
            self.together.append(frozenset(self.running))
        if len(self.running) >= together_with:
            self._gathered.set()
        try:
            if together_with > 1:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._gathered.wait(), RENDEZVOUS_SECONDS)
            else:
                await asyncio.sleep(HOLD_SECONDS)
        finally:
            self.running.discard(tag)
            self.ran[tag] = Ran(started, time.monotonic())

    def overlapped(self, first: str, second: str) -> bool:
        return any({first, second} <= moment for moment in self.together)

    def ran_before(self, first: str, second: str) -> bool:
        return self.ran[first].finished <= self.ran[second].started


PROBE = Probe()


@tool(MUTATING_TOOL)
async def order_write(tag: str) -> str:
    """Change a target."""
    await PROBE.hold(tag)
    return f"wrote {tag}"


@tool(READ_ONLY_TOOL)
async def order_read(tag: str) -> str:
    """Read a source."""
    await PROBE.hold(tag, together_with=PROBE.peers)
    return f"read {tag}"


TOOLS = [order_write, order_read]


class ArrivalShaper(AgentMiddleware[AgentState[object], None, object]):
    """Lets the calls named in *order* reach the rest of the stack one after the other, in that order.

    It sits in front of the stack, so *order* is the order in which the calls reach the conflict gate. A call is let
    through once the one before it in *order* has been, and the loop has had time to carry it into the gate. A call
    not named in *order* is not held.
    """

    def __init__(self, order: Sequence[str]) -> None:
        super().__init__()
        self.arrived: list[str] = []
        self._slots = {call_id: asyncio.Event() for call_id in order}
        self._follower = dict(itertools.pairwise(order))
        self._releases: list[asyncio.Task[None]] = []
        if order:
            self._slots[order[0]].set()

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
    ) -> ToolMessage | Command[object]:
        call_id = request.tool_call["id"] or ""
        slot = self._slots.get(call_id)
        if slot is None:
            return await handler(request)
        await slot.wait()
        self.arrived.append(call_id)
        if call_id in self._follower:
            self._releases.append(asyncio.create_task(self._release(self._follower[call_id])))
        return await handler(request)

    async def _release(self, call_id: str) -> None:
        for _ in range(SETTLE_TURNS):
            await asyncio.sleep(0)
        self._slots[call_id].set()

    async def settled(self) -> None:
        await asyncio.gather(*self._releases)


@pytest.fixture(autouse=True)
def _session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    global PROBE
    PROBE = Probe()
    monkeypatch.setitem(
        TOOL_SAFETY_METADATA, READ_ONLY_TOOL, SafetyMetadata(is_read_only=True, is_concurrent_safe=True)
    )
    monkeypatch.setitem(TOOL_SAFETY_METADATA, MUTATING_TOOL, SafetyMetadata(is_destructive=True))
    with shipped_session(tmp_path):
        yield


def _plan(shape: str) -> list[tuple[str, str]]:
    """The (call id, tool name) of each call of a message shaped like *shape*, in the model's order."""
    return [
        (f"{shape.lower()}-{position}", READ_ONLY_TOOL if kind == "S" else MUTATING_TOOL)
        for position, kind in enumerate(shape)
    ]


def _message(plan: Sequence[tuple[str, str]]) -> AIMessage:
    """One model message that makes every call of *plan* at once; the call id is also the tool's tag."""
    return AIMessage(
        content="",
        tool_calls=[{"id": call_id, "name": name, "args": {"tag": call_id}} for call_id, name in plan],
    )


def _arrival(ids: list[str], kind: str) -> list[str]:
    return ids[::-1] if kind == "reversed" else ids[1::2] + ids[0::2]


def _conflicting(shape: str) -> list[tuple[int, int]]:
    """The positions (earlier, later) of every pair of calls of which at least one is mutating."""
    return [
        (earlier, later)
        for earlier in range(len(shape))
        for later in range(earlier + 1, len(shape))
        if "E" in (shape[earlier], shape[later])
    ]


async def _run(plan: Sequence[tuple[str, str]], arrival: list[str]) -> tuple[ArrivalShaper, list[ToolMessage]]:
    shaper = ArrivalShaper(arrival)
    _, agent = shipped_agent([_message(plan), AIMessage(content="done")], TOOLS, ahead=[shaper])
    result = await asyncio.wait_for(agent.ainvoke({"messages": [HumanMessage(content="go")]}), timeout=20)
    await shaper.settled()
    return shaper, [m for m in result["messages"] if isinstance(m, ToolMessage)]


@pytest.mark.parametrize("kind", ["reversed", "odd-first"])
@pytest.mark.parametrize("shape", SHAPES)
async def test_conflicting_calls_run_in_the_models_order_whatever_order_they_reach_the_gate(
    shape: str, kind: str
) -> None:
    plan = _plan(shape)
    ids = [call_id for call_id, _ in plan]
    forced = _arrival(ids, kind)

    shaper, answers = await _run(plan, forced)

    assert shaper.arrived == forced
    assert [m.status for m in answers] == ["success"] * len(plan)
    for earlier, later in _conflicting(shape):
        assert PROBE.ran_before(ids[earlier], ids[later]), f"{ids[later]} ran before {ids[earlier]}"


async def test_read_only_calls_still_run_together_when_they_reach_the_gate_in_reverse() -> None:
    plan = _plan("SSSS")
    ids = [call_id for call_id, _ in plan]
    PROBE.peers = len(ids)

    await _run(plan, ids[::-1])

    assert max((len(moment) for moment in PROBE.together), default=0) == len(ids)


async def test_a_mutating_call_waits_for_the_read_only_calls_ahead_of_it_which_run_together() -> None:
    plan = _plan("SSE")
    first, second, mutating = (call_id for call_id, _ in plan)
    PROBE.peers = 2

    await _run(plan, [mutating, second, first])

    assert PROBE.overlapped(first, second)
    assert PROBE.ran_before(first, mutating)
    assert PROBE.ran_before(second, mutating)


async def test_a_read_only_call_behind_a_mutating_one_waits_for_it_and_one_ahead_of_it_does_not() -> None:
    plan = _plan("SES")
    before, mutating, after = (call_id for call_id, _ in plan)

    await _run(plan, [after, mutating, before])

    assert PROBE.ran_before(before, mutating)
    assert PROBE.ran_before(mutating, after)
    assert not PROBE.overlapped(before, after)


def _approve(requests: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{"type": "approve"} for _ in requests]


def _approve_edit_reject(requests: list[dict[str, object]]) -> list[dict[str, object]]:
    edited_args = {"tag": "edited"}
    return [{"type": "approve"}, {"type": "edit", "args": edited_args}, {"type": "reject", "feedback": "no"}][
        : len(requests)
    ]


def _approval_agent(shaper: ArrivalShaper, script: list[AIMessage], saver: InMemorySaver) -> CompiledStateGraph:
    return shipped_agent(script, TOOLS, checkpointer=saver, ahead=[shaper])[1]


@pytest.mark.parametrize("new_instance", [False, True])
@pytest.mark.parametrize(
    ("decide", "dispatched", "ran_tags"),
    [
        (_approve, ["eese-0", "eese-1", "eese-2", "eese-3"], ["eese-0", "eese-1", "eese-2", "eese-3"]),
        (_approve_edit_reject, ["eese-0", "eese-1", "eese-2"], ["eese-0", "edited", "eese-2"]),
    ],
    ids=["approve-all", "approve-edit-reject"],
)
async def test_approved_edited_and_rejected_calls_keep_the_models_order_after_the_run_resumes(
    decide: Callable[[list[dict[str, object]]], list[dict[str, object]]],
    dispatched: list[str],
    ran_tags: list[str],
    new_instance: bool,
) -> None:
    """The decisions arrive between the model message and its tool calls, and the resumed run may be a new instance."""
    set_security_config(SecurityConfig(yolo_mode_enabled=False, privacy_policy=PrivacyPolicy(enabled=False)))
    script = [_message(_plan("EESE")), AIMessage(content="done")]
    saver = InMemorySaver()
    thread = {"configurable": {"thread_id": "approval"}}
    first_shaper, resumed_shaper = ArrivalShaper(dispatched[::-1]), ArrivalShaper(dispatched[::-1])
    agent = _approval_agent(first_shaper, script, saver)

    paused = await asyncio.wait_for(agent.ainvoke({"messages": [HumanMessage(content="go")]}, thread), timeout=20)
    requests = paused["__interrupt__"][0].value["actionRequests"]
    assert PROBE.ran == {}
    assert len(requests) == 3

    resumer = _approval_agent(resumed_shaper, script, saver) if new_instance else agent
    await asyncio.wait_for(
        resumer.ainvoke(Command(resume={"decisions": decide(requests)}), thread),
        timeout=20,
    )

    used = resumed_shaper if new_instance else first_shaper
    await used.settled()
    assert used.arrived == dispatched[::-1]
    assert sorted(PROBE.ran) == sorted(ran_tags)
    for earlier, later in itertools.pairwise(ran_tags):
        assert PROBE.ran_before(earlier, later), f"{later} ran before {earlier}"
