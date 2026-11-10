"""ThinkingReplayGuardMiddleware: a refused replay of signed reasoning is retried once without it, for the whole run."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.middlewares.thinking_replay_guard_middleware import ThinkingReplayGuardMiddleware
from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY

_BLOCKS = [{"type": "thinking", "thinking": "plan", "signature": "sig-1"}]
_RESPONSE = ModelResponse(result=[AIMessage(content="ok")])


class _ProviderError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def _refusal() -> _ProviderError:
    return _ProviderError("messages.1.content.0: Invalid `signature` in `thinking` block", status_code=400)


def _history() -> list[AnyMessage]:
    call = {"name": "search", "args": {}, "id": "c1", "type": "tool_call"}
    return [
        HumanMessage(content="go"),
        AIMessage(content="", tool_calls=[call], additional_kwargs={THINKING_BLOCKS_KEY: _BLOCKS}),
        ToolMessage(content="found", tool_call_id="c1"),
    ]


def _request(messages: list[AnyMessage], context: dict[str, object] | None) -> ModelRequest:
    runtime = None if context is None else Runtime(context=context)
    return ModelRequest(model=AsyncMock(), messages=messages, runtime=runtime)


def _carries_blocks(request: ModelRequest) -> bool:
    return any(THINKING_BLOCKS_KEY in message.additional_kwargs for message in request.messages)


@pytest.mark.asyncio
async def test_a_request_the_provider_takes_goes_on_unchanged() -> None:
    request = _request(_history(), {})
    handler = AsyncMock(return_value=_RESPONSE)

    response = await ThinkingReplayGuardMiddleware().awrap_model_call(request, handler)

    handler.assert_awaited_once_with(request)
    assert response is _RESPONSE


@pytest.mark.asyncio
async def test_a_refused_replay_is_sent_once_more_without_the_blocks() -> None:
    messages = _history()
    handler = AsyncMock(side_effect=[_refusal(), _RESPONSE])

    response = await ThinkingReplayGuardMiddleware().awrap_model_call(_request(messages, {}), handler)

    first, second = (call.args[0] for call in handler.await_args_list)
    assert response is _RESPONSE
    assert _carries_blocks(first)
    assert not _carries_blocks(second)
    # The conversation itself keeps what the model wrote: only the request copy loses the blocks.
    assert messages[1].additional_kwargs[THINKING_BLOCKS_KEY] == _BLOCKS
    assert [m.content for m in second.messages] == [m.content for m in messages]


@pytest.mark.asyncio
async def test_the_run_replays_nothing_after_a_refusal() -> None:
    context: dict[str, object] = {}
    middleware = ThinkingReplayGuardMiddleware()
    await middleware.awrap_model_call(_request(_history(), context), AsyncMock(side_effect=[_refusal(), _RESPONSE]))

    later = AsyncMock(return_value=_RESPONSE)
    await middleware.awrap_model_call(_request(_history(), context), later)

    later.assert_awaited_once()
    assert not _carries_blocks(later.await_args_list[-1].args[0])


@pytest.mark.asyncio
async def test_another_run_starts_with_its_blocks() -> None:
    middleware = ThinkingReplayGuardMiddleware()
    await middleware.awrap_model_call(_request(_history(), {}), AsyncMock(side_effect=[_refusal(), _RESPONSE]))

    other_run = AsyncMock(return_value=_RESPONSE)
    await middleware.awrap_model_call(_request(_history(), {}), other_run)

    assert _carries_blocks(other_run.await_args_list[-1].args[0])


@pytest.mark.asyncio
async def test_a_request_without_a_run_context_is_still_retried_but_nothing_is_remembered() -> None:
    middleware = ThinkingReplayGuardMiddleware()
    first = AsyncMock(side_effect=[_refusal(), _RESPONSE])
    await middleware.awrap_model_call(_request(_history(), None), first)

    second = AsyncMock(return_value=_RESPONSE)
    await middleware.awrap_model_call(_request(_history(), None), second)

    assert first.await_count == 2
    assert _carries_blocks(second.await_args_list[-1].args[0])


@pytest.mark.asyncio
async def test_a_second_refusal_is_not_retried_again() -> None:
    handler = AsyncMock(side_effect=[_refusal(), _refusal()])

    with pytest.raises(_ProviderError):
        await ThinkingReplayGuardMiddleware().awrap_model_call(_request(_history(), {}), handler)

    assert handler.await_count == 2


@pytest.mark.asyncio
async def test_a_refusal_of_a_request_without_blocks_is_not_ours_to_retry() -> None:
    no_blocks: list[AnyMessage] = [HumanMessage(content="go")]
    handler = AsyncMock(side_effect=_refusal())

    with pytest.raises(_ProviderError):
        await ThinkingReplayGuardMiddleware().awrap_model_call(_request(no_blocks, {}), handler)

    assert handler.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [_ProviderError("rate limited", 429), _ProviderError("overloaded", 529)])
async def test_any_other_failure_goes_to_the_next_layer_untouched(failure: _ProviderError) -> None:
    context: dict[str, object] = {}
    handler = AsyncMock(side_effect=failure)

    with pytest.raises(_ProviderError) as raised:
        await ThinkingReplayGuardMiddleware().awrap_model_call(_request(_history(), context), handler)

    assert raised.value is failure
    assert handler.await_count == 1
    assert context == {}
