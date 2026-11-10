"""progress_middleware inside a tool loop: the todo focus is rendered once per run and then left byte-identical."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.meta_tools.progress.schemas import (
    TodoItem,
    TodoStatus,
    TodoStore,
)
from myrm_agent_harness.agent.middlewares.progress_middleware import progress_middleware
from myrm_agent_harness.core.message_origin import runtime_human_message


def _loop_request(
    context: dict[str, object], *extra: AnyMessage, user: str = "Please refactor auth module"
) -> ModelRequest:
    """A request of the run that owns ``context``: the user's message, then the tool-loop messages in ``extra``."""
    return ModelRequest(
        model=AsyncMock(), messages=[HumanMessage(content=user, id="u1"), *extra], runtime=Runtime(context=context)
    )


def _tool_round(call_id: str) -> list[AnyMessage]:
    return [
        AIMessage(content="", tool_calls=[{"name": "file_read", "args": {}, "id": call_id}]),
        ToolMessage(content="file content", tool_call_id=call_id),
    ]


@pytest.mark.asyncio
async def test_the_focus_is_the_same_on_every_request_of_a_run() -> None:
    """A tool loop shows the todo focus of its first request on every later one, so the cached prefix never changes."""
    first = TodoStore(goal="Refactor", todos=[TodoItem(id="t1", content="step 1", status=TodoStatus.IN_PROGRESS)])
    later = TodoStore(
        goal="Refactor", todos=[TodoItem(id="t9", content="a step the loop added", status=TodoStatus.PENDING)]
    )
    get_todos = AsyncMock(side_effect=[first, later])
    middleware = progress_middleware(get_todos)
    context: dict[str, object] = {}
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    round_one, round_two = _tool_round("c1"), _tool_round("c2")

    await middleware.awrap_model_call(_loop_request(context), handler)
    await middleware.awrap_model_call(_loop_request(context, *round_one), handler)
    await middleware.awrap_model_call(_loop_request(context, *round_one, *round_two), handler)

    sent = [call.args[0].messages for call in handler.await_args_list]
    assert sent[0][0].content == sent[1][0].content == sent[2][0].content
    assert "t1" in sent[0][0].content
    assert "t9" not in sent[2][0].content
    assert get_todos.await_count == 1
    assert sent[2][1:] == [*round_one, *round_two]


@pytest.mark.asyncio
async def test_todos_the_model_starts_in_the_middle_of_a_run_do_not_appear_halfway() -> None:
    store = TodoStore(goal="g", todos=[TodoItem(id="t1", content="step one")])
    get_todos = AsyncMock(side_effect=[None, store])
    middleware = progress_middleware(get_todos)
    context: dict[str, object] = {}
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    await middleware.awrap_model_call(_loop_request(context), handler)
    await middleware.awrap_model_call(_loop_request(context, *_tool_round("c1")), handler)

    assert [call.args[0].messages[0].content for call in handler.await_args_list] == ["Please refactor auth module"] * 2
    assert get_todos.await_count == 1


@pytest.mark.asyncio
async def test_a_new_run_renders_the_todos_it_holds_now() -> None:
    old = TodoStore(goal="g", todos=[TodoItem(id="t1", content="old step")])
    new = TodoStore(goal="g", todos=[TodoItem(id="t2", content="new step")])
    middleware = progress_middleware(AsyncMock(side_effect=[old, new]))
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    await middleware.awrap_model_call(_loop_request({}), handler)
    await middleware.awrap_model_call(_loop_request({}), handler)

    texts = [call.args[0].messages[0].content for call in handler.await_args_list]
    assert "old step" in texts[0]
    assert "new step" in texts[1]
    assert "old step" not in texts[1]


@pytest.mark.asyncio
async def test_a_request_without_a_run_context_renders_every_time() -> None:
    get_todos = AsyncMock(return_value=TodoStore(goal="g", todos=[TodoItem(id="t1", content="step one")]))
    middleware = progress_middleware(get_todos)
    request = ModelRequest(model=AsyncMock(), messages=[HumanMessage(content="hi")])
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    await middleware.awrap_model_call(request, handler)
    await middleware.awrap_model_call(request, handler)

    assert get_todos.await_count == 2


@pytest.mark.asyncio
async def test_the_focus_stays_on_the_users_message_when_the_runtime_wrote_a_notice_after_it() -> None:
    store = TodoStore(goal="g", todos=[TodoItem(id="t1", content="step one")])
    middleware = progress_middleware(AsyncMock(return_value=store))
    notice = runtime_human_message("[constraint] the sandbox has no network")
    request = ModelRequest(
        model=AsyncMock(),
        messages=[HumanMessage(content="do it", id="u1"), *_tool_round("c1"), notice],
    )
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    await middleware.awrap_model_call(request, handler)

    sent = handler.await_args_list[-1].args[0].messages
    assert "t1" in sent[0].content
    assert sent[-1] is notice


@pytest.mark.asyncio
async def test_the_focus_says_it_is_a_snapshot_of_the_turn_start() -> None:
    store = TodoStore(goal="g", todos=[TodoItem(id="t1", content="step one")])
    middleware = progress_middleware(AsyncMock(return_value=store))
    request = ModelRequest(model=AsyncMock(), messages=[HumanMessage(content="hi")])
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    await middleware.awrap_model_call(request, handler)

    assert "Snapshot from the start of this turn" in handler.await_args_list[-1].args[0].messages[0].content
