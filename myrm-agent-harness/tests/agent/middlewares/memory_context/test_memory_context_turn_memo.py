"""The model calls of one turn share one memory load, so the block stays the same while the turn runs.

A run that carries no prefetched snapshot (the OpenAI-compatible API, scheduled runs) loads the memory from the
manager. If every model call of the turn loaded again, a memory the agent saves mid-turn would change the block, and
with it the cached prompt prefix, between two calls of the same turn, and a failing store would be retried, and
waited for, on every call. A turn starts at the user's own latest message in the thread; neither a notice the runtime
appends (a recovery hint) nor a rewrite an outer middleware makes to the request (the todo focus) starts one.

[INPUT]
- agent.middlewares.memory_context.memory_context_middleware::memory_context_middleware (POS: builds the block on every model call)
- agent.middlewares._message_origin::runtime_human_message (POS: builds the notices the runtime appends behind the user's message)
- agent.middlewares.progress_middleware::progress_middleware (POS: surfaces the active todos on the message at the tail of a request)
- agent.meta_tools.progress.schemas::TodoStore, TodoItem (POS: the active todos)
- agent.skill_agent.context::get_memory_runtime_injection (POS: the injection status a call leaves for the server)

[POS]
Turn-memo guard for the load path that has no snapshot.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStore
from myrm_agent_harness.agent.middlewares._message_origin import runtime_human_message
from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import memory_context_middleware
from myrm_agent_harness.agent.middlewares.progress_middleware import progress_middleware
from myrm_agent_harness.agent.skill_agent.context import (
    get_memory_runtime_injection,
)
from myrm_agent_harness.toolkits.memory.config import RecallMode
from tests.support.memory_context_stubs import bound_manager, make_request


def _manager(get_context: AsyncMock) -> MagicMock:
    manager = MagicMock()
    manager.recall_mode = RecallMode.HYBRID
    manager.user_id = "u1"
    manager.get_context = get_context
    return manager


def _profile(**facts: str) -> dict[str, object]:
    return {"global_profile": dict(facts)}


def _runtime(context: dict[str, object]) -> Runtime[None]:
    """The hook ``Runtime`` of a run; the middlewares read nothing from it but the run context."""
    return cast("Runtime[None]", SimpleNamespace(context=context))


async def _model_call(
    manager: MagicMock,
    run_context: object,
    turn_id: str | None,
    *,
    user_message: bool = True,
    notices: Sequence[AnyMessage] = (),
) -> str | None:
    """One model call of the turn whose user message has id ``turn_id``, with ``notices`` appended behind it.

    Returns the block the call was sent, or ``None`` when it was sent none.
    """
    messages: list[AnyMessage] = [SystemMessage(content="identity")]
    if user_message:
        messages.append(HumanMessage(content="hi", id=turn_id))
    messages.extend(notices)
    request = make_request(messages=messages)
    request.runtime.context = run_context
    with bound_manager(manager):
        await memory_context_middleware.awrap_model_call(request, AsyncMock())
    if not request.override.called:
        return None
    sent = request.override.call_args.kwargs["messages"]
    return next(
        str(m.content) for m in sent if isinstance(m, SystemMessage) and "<user_memory_context" in str(m.content)
    )


async def test_a_turn_loads_the_memory_once_however_many_calls_it_makes() -> None:
    get_context = AsyncMock(return_value=_profile(name="Li Ming"))
    manager, run_context = _manager(get_context), {"k": 1}

    blocks = [await _model_call(manager, run_context, "turn-1") for _ in range(3)]

    assert get_context.await_count == 1
    assert blocks[0] is not None and "Li Ming" in blocks[0]
    assert blocks[0] == blocks[1] == blocks[2]


async def test_a_memory_saved_mid_turn_reaches_the_next_turn_and_not_the_current_one() -> None:
    stored = _profile(name="Li Ming")
    get_context = AsyncMock(side_effect=lambda **_: stored)
    manager, run_context = _manager(get_context), {"k": 1}

    first = await _model_call(manager, run_context, "turn-1")
    stored = _profile(name="Li Ming", city="Hangzhou")  # the agent saves a fact while the turn runs
    same_turn = await _model_call(manager, run_context, "turn-1")
    next_turn = await _model_call(manager, run_context, "turn-2")

    assert same_turn == first
    assert same_turn is not None and "Hangzhou" not in same_turn
    assert next_turn is not None and "Hangzhou" in next_turn
    assert get_context.await_count == 2


async def test_a_failed_load_is_logged_once_and_the_turn_runs_without_the_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    get_context = AsyncMock(side_effect=RuntimeError("store down"))
    manager, run_context = _manager(get_context), {"k": 1}

    with caplog.at_level("WARNING"):
        blocks = []
        for _ in range(3):
            blocks.append(await _model_call(manager, run_context, "turn-1"))
            assert get_memory_runtime_injection() == {"state": "not_applied", "reason": "load_error"}

    assert blocks == [None, None, None]
    assert get_context.await_count == 1
    assert caplog.text.count("Failed to load memory context") == 1


async def test_a_failed_load_is_tried_again_on_the_next_turn() -> None:
    get_context = AsyncMock(side_effect=[RuntimeError("store down"), _profile(name="Li Ming")])
    manager, run_context = _manager(get_context), {"k": 1}

    assert await _model_call(manager, run_context, "turn-1") is None
    recovered = await _model_call(manager, run_context, "turn-2")

    assert recovered is not None and "Li Ming" in recovered
    assert get_memory_runtime_injection() == {"state": "applied", "source": "fallback"}


async def test_a_timed_out_load_is_not_waited_for_again_in_the_same_turn() -> None:
    attempts = 0

    async def hang(**_: object) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(5)
        return {}

    manager = _manager(AsyncMock(side_effect=hang))
    manager._config.retrieval.timeout_seconds = 0.05
    run_context: dict[str, object] = {"k": 1}

    assert [await _model_call(manager, run_context, "turn-1") for _ in range(3)] == [None, None, None]

    assert attempts == 1
    assert get_memory_runtime_injection() == {"state": "not_applied", "reason": "load_timeout"}


async def test_a_notice_the_runtime_appends_does_not_start_a_new_turn() -> None:
    get_context = AsyncMock(return_value=_profile(name="Li Ming"))
    manager, run_context = _manager(get_context), {"k": 1}

    first = await _model_call(manager, run_context, "turn-1")
    redriven = await _model_call(manager, run_context, "turn-1", notices=[runtime_human_message("retry the last step")])

    assert get_context.await_count == 1
    assert redriven == first


async def test_a_rewrite_an_outer_middleware_makes_to_the_request_does_not_start_a_new_turn() -> None:
    """The todo focus replaces the runtime notice at the tail on the first call of a run and on no later call."""
    get_context = AsyncMock(return_value=_profile(name="Li Ming"))
    manager = _manager(get_context)
    run_context: dict[str, object] = {"k": 1}
    todos = TodoStore(goal="finish the task", todos=[TodoItem(id="t1", content="step one")])
    progress = progress_middleware(AsyncMock(return_value=todos))
    notice = runtime_human_message("the files were restored").model_copy(update={"id": "notice-1"})
    first_call: list[AnyMessage] = [SystemMessage(content="identity"), HumanMessage(content="hi", id="turn-1"), notice]
    tool_call = AIMessage(content="", tool_calls=[{"id": "c1", "name": "ping", "args": {}}])
    later_call: list[AnyMessage] = [*first_call, tool_call, ToolMessage(content="pong", tool_call_id="c1")]
    blocks: list[str] = []

    async def model(request: ModelRequest) -> ModelResponse:
        blocks.append(
            next(
                str(m.content)
                for m in request.messages
                if isinstance(m, SystemMessage) and "<user_memory_context" in str(m.content)
            )
        )
        return ModelResponse(result=[])

    async def memory_then_model(request: ModelRequest) -> ModelResponse:
        return await memory_context_middleware.awrap_model_call(request, model)

    for thread in (first_call, later_call):
        request = ModelRequest(
            model=AsyncMock(), messages=thread, state={"messages": thread}, runtime=_runtime(run_context)
        )
        with bound_manager(manager):
            await progress.awrap_model_call(request, memory_then_model)

    assert get_context.await_count == 1
    assert len(blocks) == 2 and blocks[0] == blocks[1]


async def test_a_request_built_outside_a_graph_run_takes_its_turn_from_its_own_messages() -> None:
    get_context = AsyncMock(return_value=_profile(name="Li Ming"))
    manager = _manager(get_context)
    run_context: dict[str, object] = {"k": 1}
    messages: list[AnyMessage] = [SystemMessage(content="identity"), HumanMessage(content="hi", id="turn-1")]

    for _ in range(2):
        request = ModelRequest(model=AsyncMock(), messages=messages, runtime=_runtime(run_context))
        with bound_manager(manager):
            await memory_context_middleware.awrap_model_call(request, AsyncMock())

    assert get_context.await_count == 1


async def test_every_call_loads_when_the_users_last_message_has_no_id() -> None:
    get_context = AsyncMock(return_value=_profile(name="Li Ming"))
    manager, run_context = _manager(get_context), {"k": 1}

    for _ in range(3):
        assert await _model_call(manager, run_context, None) is not None

    assert get_context.await_count == 3


async def test_every_call_loads_when_the_request_has_no_user_message() -> None:
    get_context = AsyncMock(return_value=_profile(name="Li Ming"))
    manager, run_context = _manager(get_context), {"k": 1}

    for _ in range(2):
        assert await _model_call(manager, run_context, None, user_message=False) is not None

    assert get_context.await_count == 2


async def test_every_call_loads_when_the_run_context_is_not_a_dict() -> None:
    get_context = AsyncMock(return_value=_profile(name="Li Ming"))
    manager = _manager(get_context)
    run_context = SimpleNamespace(chat_id="c1")

    for _ in range(2):
        assert await _model_call(manager, run_context, "turn-1") is not None

    assert get_context.await_count == 2


async def test_two_runs_do_not_share_a_load_even_for_the_same_turn_id() -> None:
    get_context = AsyncMock(return_value=_profile(name="Li Ming"))
    manager = _manager(get_context)

    await _model_call(manager, {"k": 1}, "turn-1")
    await _model_call(manager, {"k": 2}, "turn-1")

    assert get_context.await_count == 2


async def test_a_prefetched_snapshot_is_read_and_never_memoized() -> None:
    get_context = AsyncMock(return_value=_profile(name="Should not be used"))
    manager = _manager(get_context)
    run_context: dict[str, object] = {
        "memory_brief_snapshot": {"snapshot_id": "s1", "memory_ctx": _profile(name="Snapshot User")}
    }

    block = await _model_call(manager, run_context, "turn-1")

    assert block is not None and "Snapshot User" in block
    get_context.assert_not_called()
    assert set(run_context) == {"memory_brief_snapshot"}
