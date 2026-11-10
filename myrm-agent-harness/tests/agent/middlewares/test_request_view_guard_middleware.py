"""RequestViewGuardMiddleware: the message list the model receives is recorded on the run's cache break detector."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.infra.cache_break_detector import (
    CacheBreakDetector,
    init_cache_break_detector,
    reset_cache_break_detector,
)
from myrm_agent_harness.agent.middlewares.request_view_guard_middleware import RequestViewGuardMiddleware


@pytest.fixture
def detector() -> Iterator[CacheBreakDetector]:
    bound = init_cache_break_detector()
    yield bound
    reset_cache_break_detector()


def _request(*messages: AnyMessage) -> ModelRequest:
    return ModelRequest(model=AsyncMock(), messages=list(messages))


def _tool_round(call_id: str) -> list[AnyMessage]:
    call = {"name": "search", "args": {}, "id": call_id, "type": "tool_call"}
    return [AIMessage(content="", tool_calls=[call]), ToolMessage(content=f"result {call_id}", tool_call_id=call_id)]


async def _run(middleware: RequestViewGuardMiddleware, request: ModelRequest) -> tuple[ModelResponse, AsyncMock]:
    handler = AsyncMock(return_value=ModelResponse(result=[AIMessage(content="ok")]))
    return await middleware.awrap_model_call(request, handler), handler


@pytest.mark.asyncio
async def test_the_request_goes_on_unchanged_and_so_does_the_response(detector: CacheBreakDetector) -> None:
    request = _request(HumanMessage(content="go"))

    response, handler = await _run(RequestViewGuardMiddleware(), request)

    handler.assert_awaited_once_with(request)
    assert response is handler.return_value


@pytest.mark.asyncio
async def test_without_a_detector_the_call_is_just_passed_on() -> None:
    reset_cache_break_detector()
    request = _request(HumanMessage(content="go"))

    response, handler = await _run(RequestViewGuardMiddleware(), request)

    handler.assert_awaited_once_with(request)
    assert response is handler.return_value


@pytest.mark.asyncio
async def test_a_loop_that_only_appends_shifts_nothing(detector: CacheBreakDetector) -> None:
    middleware = RequestViewGuardMiddleware()
    user = HumanMessage(content="go")
    first_round, second_round = _tool_round("c1"), _tool_round("c2")

    await _run(middleware, _request(user))
    await _run(middleware, _request(user, *first_round))
    await _run(middleware, _request(user, *first_round, *second_round))

    assert detector.consume_prefix_shift() is None


@pytest.mark.asyncio
async def test_a_request_that_edits_an_earlier_message_is_named(detector: CacheBreakDetector) -> None:
    middleware = RequestViewGuardMiddleware()
    first_round = _tool_round("c1")

    await _run(middleware, _request(HumanMessage(content="go"), *first_round))
    await _run(middleware, _request(HumanMessage(content="go\n\nreminder"), *first_round, *_tool_round("c2")))

    shift = detector.consume_prefix_shift()

    assert shift is not None
    assert (shift.first_index, shift.previous_length, shift.current_length) == (0, 3, 5)
    assert not shift.announced


@pytest.mark.asyncio
async def test_a_cache_breakpoint_that_moved_is_not_an_edit(detector: CacheBreakDetector) -> None:
    middleware = RequestViewGuardMiddleware()
    user = HumanMessage(content="go")
    marked = user.model_copy(update={"additional_kwargs": {"cache_control": {"type": "ephemeral"}}})

    await _run(middleware, _request(marked))
    await _run(middleware, _request(user, *_tool_round("c1")))

    assert detector.consume_prefix_shift() is None
