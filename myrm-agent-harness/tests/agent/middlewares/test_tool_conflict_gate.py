"""ToolConflictGateMiddleware: safe calls share, every other call runs alone and in the model's order among the calls of
its message, a failed call changes nothing for the rest."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, call, patch

import pytest
from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares.concurrency.tool_conflict_gate import ToolConflictGateMiddleware

SAFE = ("file_read_tool", "grep_tool")
UNSAFE = ("file_write_tool", "bash_code_execute_tool")
RECORD = "myrm_agent_harness.agent.middlewares.concurrency.tool_conflict_gate.record_tool_order"
GRACE = 5.0


async def _settle() -> None:
    for _ in range(8):
        await asyncio.sleep(0)


class FrozenClock:
    """Holds the running loop's clock still, so a grace period ends when the test says so, not when the machine does."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        loop = asyncio.get_running_loop()
        self._now = loop.time()
        monkeypatch.setattr(loop, "time", lambda: self._now)

    async def pass_time(self, seconds: float) -> None:
        self._now += seconds
        await _settle()


def _turn(call_ids: dict[str, str], message_id: str | None = "turn-1") -> dict[str, list[BaseMessage]]:
    """The state a tool task is handed: the model message that made *call_ids* (id to tool name)."""
    calls = [{"id": call_id, "name": name, "args": {}} for call_id, name in call_ids.items()]
    return {"messages": [AIMessage(content="", id=message_id, tool_calls=calls)]}


def _request(name: str, call_id: str, state: object = None) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "id": call_id, "args": {}, "type": "tool_call"},
        tool=None,
        state={"messages": []} if state is None else state,
        runtime=MagicMock(),
    )


class Calls:
    """Runs calls through one middleware; each call's handler waits until the test lets it finish."""

    def __init__(self, middleware: ToolConflictGateMiddleware | None = None) -> None:
        self.middleware = middleware or ToolConflictGateMiddleware()
        self.log: list[str] = []
        self.tasks: dict[str, asyncio.Task[ToolMessage | Command[object]]] = {}
        self._release: dict[str, asyncio.Event] = {}
        self._result: dict[str, ToolMessage] = {}

    async def start(self, name: str, call_id: str, state: object = None) -> asyncio.Task[ToolMessage | Command[object]]:
        self._release[call_id] = asyncio.Event()
        task = asyncio.create_task(self.middleware.awrap_tool_call(_request(name, call_id, state), self._handle))
        self.tasks[call_id] = task
        await _settle()
        return task

    async def _handle(self, request: ToolCallRequest) -> ToolMessage:
        call_id = request.tool_call["id"] or ""
        self.log.append(f"{call_id}+")
        await self._release[call_id].wait()
        self.log.append(f"{call_id}-")
        return self._result.get(call_id, ToolMessage(content="ok", tool_call_id=call_id))

    async def finish(self, call_id: str, result: ToolMessage | None = None) -> None:
        if result is not None:
            self._result[call_id] = result
        self._release[call_id].set()
        await _settle()


async def _answer(task: asyncio.Task[ToolMessage | Command[object]]) -> ToolMessage | Command[object]:
    """What a call answered once it is let through; a call that never gets through fails the test instead of hanging it."""
    return await asyncio.wait_for(task, timeout=1)


def _failure(call_id: str, name: str) -> ToolMessage:
    return ToolMessage(content="boom", name=name, tool_call_id=call_id, status="error")


async def test_concurrency_safe_calls_run_together() -> None:
    calls = Calls()

    await calls.start(SAFE[0], "a")
    await calls.start(SAFE[1], "b")

    assert calls.log == ["a+", "b+"]


async def test_calls_that_are_not_concurrency_safe_never_run_together() -> None:
    calls = Calls()
    await calls.start(UNSAFE[0], "a")
    await calls.start(UNSAFE[1], "b")
    assert calls.log == ["a+"]

    await calls.finish("a")

    assert calls.log == ["a+", "a-", "b+"]


@pytest.mark.parametrize(("first", "second"), [(SAFE[0], UNSAFE[0]), (UNSAFE[0], SAFE[0])])
async def test_a_call_that_is_not_concurrency_safe_never_overlaps_a_safe_one_whichever_comes_first(
    first: str, second: str
) -> None:
    calls = Calls()
    await calls.start(first, "a")
    await calls.start(second, "b")
    assert calls.log == ["a+"]

    await calls.finish("a")

    assert calls.log == ["a+", "a-", "b+"]


@pytest.mark.parametrize("name", ["mcp__weather__lookup", "undeclared_tool", ""])
async def test_a_tool_nobody_declared_is_treated_as_unsafe(name: str) -> None:
    calls = Calls()
    await calls.start(SAFE[0], "a")

    await calls.start(name, "b")

    assert calls.log == ["a+"]


async def test_a_waiting_call_does_not_hold_back_one_that_arrived_before_it() -> None:
    calls = Calls()
    await calls.start(SAFE[0], "reader")
    await calls.start(UNSAFE[0], "writer")

    await calls.finish("reader")

    assert calls.log == ["reader+", "reader-", "writer+"]


async def test_the_next_call_runs_after_a_handler_raised() -> None:
    middleware = ToolConflictGateMiddleware()

    async def failing(request: ToolCallRequest) -> ToolMessage:
        raise ValueError("tool failed")

    with pytest.raises(ValueError, match="tool failed"):
        await middleware.awrap_tool_call(_request(UNSAFE[0], "a"), failing)

    async def fine(request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="recovered", tool_call_id="b")

    async with asyncio.timeout(1):
        answer = await middleware.awrap_tool_call(_request(UNSAFE[0], "b"), fine)
    assert isinstance(answer, ToolMessage)
    assert answer.content == "recovered"


async def test_a_call_cancelled_while_waiting_lets_the_later_ones_run() -> None:
    calls = Calls()
    await calls.start(SAFE[0], "reader")
    writer = await calls.start(UNSAFE[0], "writer")
    await calls.start(SAFE[1], "late")
    assert calls.log == ["reader+"]

    writer.cancel()
    await _settle()

    assert calls.log == ["reader+", "late+"]


async def test_agents_do_not_hold_each_other_back() -> None:
    first, second = Calls(), Calls()

    await first.start(UNSAFE[0], "a")
    await second.start(UNSAFE[0], "b")

    assert first.log == ["a+"]
    assert second.log == ["b+"]


@pytest.mark.parametrize("name", [SAFE[0], UNSAFE[0]])
async def test_a_command_result_is_passed_through(name: str) -> None:
    command: Command[object] = Command(update={"x": 1})

    async def handler(request: ToolCallRequest) -> Command[object]:
        return command

    assert await ToolConflictGateMiddleware().awrap_tool_call(_request(name, "a"), handler) is command


@pytest.mark.parametrize("later", [UNSAFE[1], SAFE[0]])
async def test_a_failed_unsafe_call_does_not_stop_the_later_calls_of_its_turn(later: str) -> None:
    calls = Calls()
    state = _turn({"a": UNSAFE[0], "b": later})
    await calls.start(UNSAFE[0], "a", state)
    second = await calls.start(later, "b", state)

    await calls.finish("a", _failure("a", UNSAFE[0]))
    await calls.finish("b")

    answer = await _answer(second)
    assert isinstance(answer, ToolMessage)
    assert (answer.status, answer.content) == ("success", "ok")
    assert calls.log == ["a+", "a-", "b+", "b-"]


async def test_the_first_call_of_a_message_does_not_wait_for_the_calls_behind_it() -> None:
    calls = Calls()

    await calls.start(UNSAFE[0], "a", _turn({"a": UNSAFE[0], "b": UNSAFE[1]}))

    assert calls.log == ["a+"]


async def test_a_call_waits_for_the_conflicting_calls_ahead_of_it_to_reach_the_gate() -> None:
    calls = Calls()
    state = _turn({"a": UNSAFE[0], "b": UNSAFE[1]})

    await calls.start(UNSAFE[1], "b", state)
    assert calls.log == []

    await calls.start(UNSAFE[0], "a", state)
    assert calls.log == ["a+"]

    await calls.finish("a")
    assert calls.log == ["a+", "a-", "b+"]


async def test_concurrency_safe_calls_of_one_message_do_not_wait_for_each_other_to_reach_the_gate() -> None:
    calls = Calls()
    state = _turn({"a": SAFE[0], "b": SAFE[1]})

    await calls.start(SAFE[1], "b", state)
    await calls.start(SAFE[0], "a", state)

    assert calls.log == ["b+", "a+"]


async def test_a_concurrency_safe_call_waits_only_for_the_calls_ahead_of_it_that_are_not() -> None:
    calls = Calls()
    state = _turn({"r1": SAFE[0], "w": UNSAFE[0], "r2": SAFE[1]})

    await calls.start(SAFE[1], "r2", state)
    assert calls.log == []

    await calls.start(SAFE[0], "r1", state)
    assert calls.log == ["r1+"]

    await calls.start(UNSAFE[0], "w", state)
    assert calls.log == ["r1+"]

    await calls.finish("r1")
    assert calls.log == ["r1+", "r1-", "w+"]

    await calls.finish("w")
    assert calls.log == ["r1+", "r1-", "w+", "w-", "r2+"]


async def test_a_call_cancelled_while_waiting_to_reach_the_gate_does_not_keep_the_calls_behind_it_waiting() -> None:
    calls = Calls()
    state = _turn({"a": UNSAFE[0], "b": UNSAFE[1], "c": UNSAFE[0]})
    await calls.start(UNSAFE[0], "c", state)
    cancelled = await calls.start(UNSAFE[1], "b", state)
    cancelled.cancel()
    await _settle()

    await calls.start(UNSAFE[0], "a", state)
    await calls.finish("a")

    assert calls.log == ["a+", "a-", "c+"]


async def test_a_call_does_not_wait_for_a_call_ahead_of_it_that_already_has_an_answer() -> None:
    calls = Calls()
    state = _turn({"a": UNSAFE[0], "b": UNSAFE[1]})
    state["messages"].append(ToolMessage(content="done", tool_call_id="a"))

    with patch(RECORD) as record:
        await calls.start(UNSAFE[1], "b", state)

    assert calls.log == ["b+"]
    record.assert_not_called()


async def test_a_call_stops_waiting_for_a_call_that_never_reaches_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FrozenClock(monkeypatch)
    calls = Calls(ToolConflictGateMiddleware(arrival_grace_seconds=GRACE))
    state = _turn({"a": UNSAFE[0], "b": UNSAFE[1]})

    with patch(RECORD) as record:
        await calls.start(UNSAFE[1], "b", state)
        await clock.pass_time(GRACE / 2)
        assert calls.log == []
        await clock.pass_time(GRACE)

    assert calls.log == ["b+"]
    assert record.call_args_list == [call("held_for_order"), call("predecessor_absent")]


async def test_a_call_that_was_written_off_is_not_waited_for_again_and_still_runs_when_it_arrives_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FrozenClock(monkeypatch)
    calls = Calls(ToolConflictGateMiddleware(arrival_grace_seconds=GRACE))
    state = _turn({"a": UNSAFE[0], "b": UNSAFE[1], "c": UNSAFE[0]})

    with patch(RECORD) as record:
        await calls.start(UNSAFE[1], "b", state)
        await clock.pass_time(GRACE * 2)
        await calls.start(UNSAFE[0], "c", state)
        await calls.start(UNSAFE[0], "a", state)

    assert record.call_args_list == [call("held_for_order"), call("predecessor_absent")]
    assert calls.log == ["b+"]

    for call_id in ("b", "c", "a"):
        await calls.finish(call_id)

    assert calls.log == ["b+", "b-", "c+", "c-", "a+", "a-"]


async def test_a_message_that_cannot_be_told_apart_is_admitted_in_arrival_order_and_counted() -> None:
    calls = Calls()
    state = _turn({"a": UNSAFE[0], "b": UNSAFE[1]}, message_id=None)

    with patch(RECORD) as record:
        await calls.start(UNSAFE[1], "b", state)

    assert calls.log == ["b+"]
    record.assert_called_once_with("turn_unidentified")


async def test_a_message_with_a_single_call_is_neither_ordered_nor_counted() -> None:
    calls = Calls()

    with patch(RECORD) as record:
        await calls.start(UNSAFE[0], "a", _turn({"a": UNSAFE[0]}))

    assert calls.log == ["a+"]
    record.assert_not_called()


async def test_a_call_held_for_its_predecessors_is_counted_once() -> None:
    calls = Calls()
    state = _turn({"a": UNSAFE[0], "b": UNSAFE[1]})

    with patch(RECORD) as record:
        await calls.start(UNSAFE[1], "b", state)
        await calls.start(UNSAFE[0], "a", state)

    record.assert_called_once_with("held_for_order")
