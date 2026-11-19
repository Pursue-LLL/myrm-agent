"""McpWarmupMiddleware: sessions start with the first model request; a response that calls tools waits for them.

[INPUT]
- myrm_agent_harness.agent.middlewares.mcp_warmup_middleware::McpWarmupMiddleware (POS: unit under test)
- myrm_agent_harness.toolkits.mcp.warmup::McpWarmup (POS: the warm-up whose barrier it drives)
- myrm_agent_harness.agent._internals._agent_build::build_middlewares (POS: where host middlewares join the chain)
- tests.support.mcp_warmup_doubles (POS: the pool double and the tool builders)

[OUTPUT]
- Unit tests for when the sessions start, which responses wait, and that the middleware joins the assembled chain.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares.mcp_warmup_middleware import McpWarmupMiddleware
from myrm_agent_harness.toolkits.mcp.tool_table_store import ToolTableStore
from myrm_agent_harness.toolkits.mcp.warmup import McpWarmup
from tests.support.mcp_warmup_doubles import FakeConnection, FakePool, config, live_tools, table_of

type _Handler = Callable[[ModelRequest[None]], Awaitable[ModelResponse[object]]]

_REQUEST = cast(ModelRequest[None], object())
_TEXT = ModelResponse(result=[AIMessage(content="answer")])
_TOOL_CALL = ModelResponse(
    result=[AIMessage(content="", tool_calls=[{"name": "bash_code_execute_tool", "args": {}, "id": "call-1"}])]
)


class _Warmup:
    """The two members of McpWarmup the middleware calls, with a settle the test can hold open."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.release = asyncio.Event()
        self.release.set()

    def start(self) -> None:
        self.events.append("start")

    async def settle(self) -> None:
        self.events.append("settle")
        await self.release.wait()
        self.events.append("settled")


def _handler(events: list[str], response: ModelResponse[object]) -> _Handler:
    async def handler(request: ModelRequest[None]) -> ModelResponse[object]:
        events.append("model")
        return response

    return handler


async def _wrap(middleware: McpWarmupMiddleware, handler: _Handler) -> ModelResponse[object]:
    return await middleware.awrap_model_call(_REQUEST, handler)


async def test_the_sessions_start_before_the_model_is_asked() -> None:
    events: list[str] = []
    middleware = McpWarmupMiddleware(cast(McpWarmup, _Warmup(events)))

    await _wrap(middleware, _handler(events, _TEXT))

    assert events == ["start", "model"]


async def test_a_text_answer_never_waits() -> None:
    events: list[str] = []
    warmup = _Warmup(events)
    warmup.release.clear()
    middleware = McpWarmupMiddleware(cast(McpWarmup, warmup))

    response = await asyncio.wait_for(_wrap(middleware, _handler(events, _TEXT)), timeout=1)

    assert response is _TEXT
    assert "settle" not in events


async def test_a_response_that_calls_tools_waits_for_the_sessions() -> None:
    events: list[str] = []
    warmup = _Warmup(events)
    warmup.release.clear()
    middleware = McpWarmupMiddleware(cast(McpWarmup, warmup))

    waiting = asyncio.create_task(_wrap(middleware, _handler(events, _TOOL_CALL)))
    await asyncio.sleep(0.05)
    assert not waiting.done()
    assert events == ["start", "model", "settle"]

    warmup.release.set()
    assert await asyncio.wait_for(waiting, timeout=1) is _TOOL_CALL
    assert events == ["start", "model", "settle", "settled"]


async def test_a_model_error_propagates_without_waiting() -> None:
    events: list[str] = []

    async def failing(request: ModelRequest[None]) -> ModelResponse[object]:
        raise RuntimeError("provider down")

    middleware = McpWarmupMiddleware(cast(McpWarmup, _Warmup(events)))

    with pytest.raises(RuntimeError, match="provider down"):
        await _wrap(middleware, failing)

    assert events == ["start"]


async def test_tool_calls_are_held_until_the_live_session_is_up(tmp_path: Path) -> None:
    """The real warm-up: the first request leaves with nothing connected; the tools it calls wait for the session."""
    store = ToolTableStore(tmp_path)
    store.save("hash-demo", table_of("a", "b"))
    pool = FakePool()
    pool.live["demo"] = FakeConnection("demo", live_tools("a", "b"))
    pool.gate = asyncio.Event()
    warmup = McpWarmup(store)
    await warmup.serve(pool, [config()], threshold=0)
    middleware = McpWarmupMiddleware(warmup)
    seen_pending_at_request: list[list[str]] = []

    async def model(request: ModelRequest[None]) -> ModelResponse[object]:
        await asyncio.sleep(0)
        seen_pending_at_request.append(list(pool.asked))
        return _TOOL_CALL

    waiting = asyncio.create_task(_wrap(middleware, model))
    await asyncio.sleep(0.05)

    assert seen_pending_at_request == [[]]
    assert pool.asked == ["demo"]
    assert not waiting.done()

    pool.gate.set()
    assert await asyncio.wait_for(waiting, timeout=5) is _TOOL_CALL
    assert not warmup._inflight


def test_the_middleware_joins_the_assembled_chain_once() -> None:
    middleware = McpWarmupMiddleware(cast(McpWarmup, _Warmup([])))

    chain = build_middlewares(create_registry(), [middleware])

    assert sum(item is middleware for item in chain) == 1
