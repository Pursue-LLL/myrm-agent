"""ModelCallCancelMiddleware: a stop aborts an in-flight model request, and nothing else changes.

[INPUT]
- myrm_agent_harness.agent.middlewares.model_call_cancel::ModelCallCancelMiddleware (POS: unit under test)
- myrm_agent_harness.agent._internals._agent_build::build_middlewares (POS: where the middleware is wired)
- myrm_agent_harness.utils.runtime.cancellation (POS: the token the request is raced against)

[OUTPUT]
- Unit tests for the model-call wrapper and for its position in the assembled chain.

[POS]
Unit tests mirroring src/myrm_agent_harness/agent/middlewares/model_call_cancel.py.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from typing import cast

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares.model_call_cancel import ModelCallCancelMiddleware
from myrm_agent_harness.agent.middlewares.rate_limit import RateLimitMiddleware
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationToken,
    CancelReason,
    OperationCancelledError,
    set_cancel_token,
)

_REQUEST = cast(ModelRequest, object())
_ANSWER = ModelResponse(result=[AIMessage(content="answer")])


@pytest.fixture(autouse=True)
def _clean_run_state() -> Iterator[None]:
    yield
    set_cancel_token(None)


class _Handler:
    """A model request that stays silent for ``seconds`` and records whether the stop cancelled it."""

    def __init__(self, seconds: float, error: Exception | None = None) -> None:
        self._seconds = seconds
        self._error = error
        self.started = asyncio.Event()
        self.cancelled = False

    async def __call__(self, request: ModelRequest) -> ModelResponse:
        self.started.set()
        try:
            await asyncio.sleep(self._seconds)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self._error is not None:
            raise self._error
        return _ANSWER


@pytest.mark.asyncio
async def test_outside_a_run_the_request_is_simply_awaited() -> None:
    handler = _Handler(0.01)

    result = await ModelCallCancelMiddleware().awrap_model_call(_REQUEST, handler)

    assert result is _ANSWER


@pytest.mark.asyncio
async def test_a_stop_during_the_request_aborts_it_within_a_poll_interval() -> None:
    token = CancellationToken("unit_stop")
    set_cancel_token(token)
    handler = _Handler(3600.0)
    call = asyncio.create_task(ModelCallCancelMiddleware().awrap_model_call(_REQUEST, handler))
    await asyncio.wait_for(handler.started.wait(), timeout=5.0)

    stopped_at = time.monotonic()
    token.cancel(CancelReason.USER_CANCELLED)
    with pytest.raises(OperationCancelledError):
        await asyncio.wait_for(call, timeout=5.0)

    assert time.monotonic() - stopped_at < 2.0
    assert handler.cancelled, "the request the stop interrupted must not keep running behind the ended turn"


@pytest.mark.asyncio
async def test_a_stop_set_before_the_request_never_starts_it() -> None:
    token = CancellationToken("unit_stop_before")
    token.cancel(CancelReason.USER_CANCELLED)
    set_cancel_token(token)
    handler = _Handler(0.01)

    with pytest.raises(OperationCancelledError):
        await ModelCallCancelMiddleware().awrap_model_call(_REQUEST, handler)

    assert not handler.started.is_set()


@pytest.mark.asyncio
async def test_a_request_error_reaches_the_caller_unchanged() -> None:
    """A real provider failure must stay a provider failure, so failover and retry still see it."""
    set_cancel_token(CancellationToken("unit_error"))
    boom = RuntimeError("provider exploded")

    with pytest.raises(RuntimeError) as raised:
        await ModelCallCancelMiddleware().awrap_model_call(_REQUEST, _Handler(0.01, error=boom))

    assert raised.value is boom


@pytest.mark.asyncio
async def test_a_request_nobody_stops_returns_its_response_under_a_live_token() -> None:
    set_cancel_token(CancellationToken("unit_no_stop"))

    result = await ModelCallCancelMiddleware().awrap_model_call(_REQUEST, _Handler(0.3))

    assert result is _ANSWER


def test_the_assembled_chain_wraps_every_other_model_call_wrapper() -> None:
    """First in the list is outermost, so a cut also reaches the backoff sleeps and retries of the wrappers inside."""
    chain = build_middlewares(create_registry(), [RateLimitMiddleware()])

    names = [type(middleware).__name__ for middleware in chain]

    assert names[0] == "ModelCallCancelMiddleware"
    assert names.index("ModelCallCancelMiddleware") < names.index("RateLimitMiddleware")
