"""One run's requests in the stack an agent ships: does each request extend the one before it?

A provider caches the prefix of a request, and a reasoning block it signed is valid only under the exact bytes that
preceded it. Within one run (one tool loop) every request therefore has to start with the whole of the request
before. The unit tests of a notice writer hand it a mocked request; the writers meet each other, and the run
context that carries their memory, only in the compiled graph. These tests compile the shipped stack with
``create_agent`` around a scripted model and compare what the model is sent on every call of a loop.

[INPUT]
- agent._internals._agent_build::build_middlewares, create_registry (POS: the middleware stack an agent runs)
- agent.middlewares._session_context::get_terminal_errors, set_goal_provider (POS: the per-run session context the stack reads)
- agent.meta_tools.progress.storage::write_todos_sync_to_workspace (POS: the todo list the focus injection reads)
- tests.support.shipped_graph::ScriptedModel, shipped_session (POS: scripted model that records what each call was sent)

[POS]
Graph-level guard of the loop-stable request view: todo focus, circuit-breaker constraints, goal focus and runtime
notices composed in one run.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain.agents.middleware.types import InputAgentState
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langgraph.graph.state import CompiledStateGraph

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStatus, TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import write_todos_sync_to_workspace
from myrm_agent_harness.agent.middlewares._session_context import get_terminal_errors, set_goal_provider
from myrm_agent_harness.agent.tool_management import ToolRegistry, ToolSource
from myrm_agent_harness.core.message_origin import runtime_human_message
from tests.support.shipped_graph import ScriptedModel, shipped_session

_IDENTITY = "You are the test agent."
_THREAD: RunnableConfig = {"configurable": {"thread_id": "view-stability"}}
_TODO_BLOCK = "## Task progress (active todos)"
_CONSTRAINTS = "[SYSTEM_ENFORCED] Environment capability constraints detected:"

type Call = list[tuple[str, str]]


@tool
def ping() -> str:
    """Answer pong."""
    return "pong"


@tool
def trip_network() -> str:
    """Make the run's circuit breaker report the network as blocked."""
    get_terminal_errors().add("network_blocked")
    return "tripped"


@tool
def trip_filesystem() -> str:
    """Make the run's circuit breaker report the filesystem as read-only."""
    get_terminal_errors().add("sandbox_ro")
    return "tripped"


def _todo_write(workspace: Path, after: TodoStore) -> BaseTool:
    @tool("todo_write")
    def todo_write() -> str:
        """Replace the todo list with the finished one."""
        write_todos_sync_to_workspace(str(workspace), after)
        return "saved"

    return todo_write


def _loop(*tool_names: str) -> list[AIMessage]:
    """A script that calls each tool once, one per model call, and then answers."""
    calls = [
        AIMessage(content="", tool_calls=[{"id": f"c{n}", "name": name, "args": {}}])
        for n, name in enumerate(tool_names)
    ]
    return [*calls, AIMessage(content="done")]


def _graph(
    model: ScriptedModel,
    tools: Sequence[BaseTool],
    *,
    registry: ToolRegistry | None = None,
    extra_middlewares: Sequence[object] = (),
) -> CompiledStateGraph:
    middlewares = build_middlewares(registry or create_registry(), list(extra_middlewares), None)
    return create_agent(model, tools=list(tools), middleware=middlewares, system_prompt=_IDENTITY)


async def _run(graph: CompiledStateGraph, workspace: Path, messages: Sequence[AnyMessage]) -> None:
    """One run, driven as the stream executor drives it: the run context is the graph's ``context``."""
    context: dict[str, object] = {"chat_id": "view-stability", "workspace_path": str(workspace)}
    with shipped_session(workspace):
        await graph.ainvoke(cast("InputAgentState", {"messages": list(messages), **context}), _THREAD, context=context)


def _assert_each_request_extends_the_one_before(calls: list[Call]) -> None:
    for number, (earlier, later) in enumerate(itertools.pairwise(calls), start=1):
        edited = next(
            (i for i, (before, after) in enumerate(zip(earlier, later, strict=False)) if before != after), None
        )
        assert edited is None and len(later) >= len(earlier), (
            f"request {number + 1} edits message {edited} of request {number}"
        )


def _text_of_user_message(call: Call, start: str) -> str:
    return next(text for kind, text in call if kind == "HumanMessage" and text.startswith(start))


def _constraint_notices(call: Call) -> list[str]:
    return [text for kind, text in call if kind == "HumanMessage" and text.startswith(_CONSTRAINTS)]


def _items(*, status: TodoStatus) -> list[TodoItem]:
    return [
        TodoItem(id="t1", content="first step", status=status),
        TodoItem(id="t2", content="second step", status=status),
    ]


async def test_the_todo_focus_is_one_text_on_every_request_even_when_the_list_changes_midway(tmp_path: Path) -> None:
    write_todos_sync_to_workspace(str(tmp_path), TodoStore(goal="Ship it", todos=_items(status=TodoStatus.PENDING)))
    todo_write = _todo_write(tmp_path, TodoStore(goal="Ship it", todos=_items(status=TodoStatus.COMPLETED)))
    registry = create_registry()
    registry.register(todo_write, source=ToolSource.USER)
    model = ScriptedModel(script=_loop("todo_write", "ping"))

    await _run(_graph(model, [todo_write, ping], registry=registry), tmp_path, [HumanMessage(content="build it")])

    assert len(model.calls) == 3
    _assert_each_request_extends_the_one_before(model.calls)
    focus = [_text_of_user_message(call, "build it") for call in model.calls]
    assert _TODO_BLOCK in focus[0]
    assert "[pending] t1: first step" in focus[0]
    assert focus[1] == focus[2] == focus[0], "the todos the model finished must not rewrite the user's message"


async def test_constraints_the_breaker_reports_midway_are_written_once_and_stay_in_place(tmp_path: Path) -> None:
    model = ScriptedModel(script=_loop("ping", "trip_network", "ping", "trip_filesystem", "ping"))

    await _run(_graph(model, [ping, trip_network, trip_filesystem]), tmp_path, [HumanMessage(content="build it")])

    assert len(model.calls) == 6
    _assert_each_request_extends_the_one_before(model.calls)
    assert [len(_constraint_notices(call)) for call in model.calls] == [0, 0, 1, 1, 2, 2]
    (first,) = _constraint_notices(model.calls[2])
    assert "Network access is BLOCKED" in first
    assert "READ-ONLY" not in first
    first_notice, second_notice = _constraint_notices(model.calls[-1])
    assert first_notice == first, "a notice, once written, keeps its text"
    assert "READ-ONLY" in second_notice
    assert model.calls[-1].index(("HumanMessage", first)) == model.calls[2].index(("HumanMessage", first))


async def test_the_goal_line_stays_on_the_user_message_while_the_loop_goes_on(tmp_path: Path) -> None:
    goal = Goal(goal_id="g-1", session_id="view-stability", objective="Refactor auth", status=GoalStatus.ACTIVE)
    provider = AsyncMock()
    provider.get_active_goal.return_value = goal
    set_goal_provider(provider)
    model = ScriptedModel(script=_loop("trip_network", "ping"))
    try:
        await _run(_graph(model, [ping, trip_network]), tmp_path, [HumanMessage(content="build it")])
    finally:
        set_goal_provider(None)

    _assert_each_request_extends_the_one_before(model.calls)
    for call in model.calls:
        assert _text_of_user_message(call, "build it").count("Active goal: Refactor auth") == 1
    assert len(_constraint_notices(model.calls[-1])) == 1


async def test_a_run_with_todos_a_goal_a_breaker_trip_and_a_recovery_hint_never_edits_an_earlier_request(
    tmp_path: Path,
) -> None:
    write_todos_sync_to_workspace(str(tmp_path), TodoStore(goal="Ship it", todos=_items(status=TodoStatus.PENDING)))
    todo_write = _todo_write(tmp_path, TodoStore(goal="Ship it", todos=_items(status=TodoStatus.COMPLETED)))
    registry = create_registry()
    registry.register(todo_write, source=ToolSource.USER)
    provider = AsyncMock()
    provider.get_active_goal.return_value = Goal(
        goal_id="g-1", session_id="view-stability", objective="Refactor auth", status=GoalStatus.ACTIVE
    )
    set_goal_provider(provider)
    hint = "[Recovery] The previous stream was cut; carry on from the last result."
    model = ScriptedModel(script=_loop("todo_write", "trip_network", "ping"))
    try:
        await _run(
            _graph(model, [todo_write, ping, trip_network], registry=registry),
            tmp_path,
            [HumanMessage(content="build it"), runtime_human_message(hint)],
        )
    finally:
        set_goal_provider(None)

    assert len(model.calls) == 4
    _assert_each_request_extends_the_one_before(model.calls)
    user_message = _text_of_user_message(model.calls[0], "build it")
    assert _TODO_BLOCK in user_message
    assert "Active goal: Refactor auth" in user_message
    assert ("HumanMessage", hint) in model.calls[0], "the recovery hint is kept as the runtime wrote it"
    assert model.calls[0].index(("HumanMessage", hint)) > model.calls[0].index(("HumanMessage", user_message))
    assert len(_constraint_notices(model.calls[-1])) == 1


async def test_the_check_notices_a_middleware_that_edits_the_users_message_between_requests(tmp_path: Path) -> None:
    requests_seen = 0

    @wrap_model_call(name="counting_middleware")
    async def counting(request: ModelRequest, handler: object) -> ModelResponse:
        nonlocal requests_seen
        requests_seen += 1
        messages = list(request.messages)
        user = messages[0]
        messages[0] = user.model_copy(update={"content": f"{user.content} (request {requests_seen})"})
        return await cast("AsyncMock", handler)(request.override(messages=messages))

    model = ScriptedModel(script=_loop("ping"))
    await _run(_graph(model, [ping], extra_middlewares=[counting]), tmp_path, [HumanMessage(content="build it")])

    with pytest.raises(AssertionError, match="request 2 edits message"):
        _assert_each_request_extends_the_one_before(model.calls)
