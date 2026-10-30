"""ParallelToolCallsMiddleware: the engine's parallel-tool-calls switch reaches the provider as a setting of the model call.

[INPUT]
- myrm_agent_harness.agent.middlewares.parallel_tool_calls::ParallelToolCallsMiddleware (POS: unit under test)
- myrm_agent_harness.agent._internals._agent_build::build_middlewares (POS: where the middleware is wired from ``EngineParams``)
- tests.support.shipped_graph (POS: the graph a run builds, over a model that records how it was bound)

[OUTPUT]
- Unit tests of the model-call wrapper, and tests on the shipped graph that every model call which offers tools is bound with the setting.

[POS]
Unit tests mirroring src/myrm_agent_harness/agent/middlewares/parallel_tool_calls.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares.parallel_tool_calls import ParallelToolCallsMiddleware
from myrm_agent_harness.agent.types import EngineParams
from tests.support.shipped_graph import ScriptedModel, shipped_agent, shipped_session

_ANSWER = ModelResponse(result=[AIMessage(content="answer")])


@tool
def ping() -> str:
    """Answer pong."""
    return "pong"


class _Handler:
    """The rest of the chain: keeps the request it was handed."""

    def __init__(self) -> None:
        self.received: ModelRequest | None = None

    async def __call__(self, request: ModelRequest) -> ModelResponse:
        self.received = request
        return _ANSWER


def _request(*, tools: list, model_settings: dict[str, object] | None = None) -> ModelRequest:
    return ModelRequest(model=ScriptedModel(script=[]), messages=[], tools=tools, model_settings=model_settings)


async def _through(
    middleware: ParallelToolCallsMiddleware, request: ModelRequest
) -> tuple[ModelRequest, ModelResponse]:
    handler = _Handler()
    response = await middleware.awrap_model_call(request, handler)
    assert handler.received is not None
    return handler.received, response


@pytest.mark.parametrize("parallel", [True, False])
async def test_a_model_call_with_tools_carries_the_setting(parallel: bool) -> None:
    request = _request(tools=[ping], model_settings={"temperature": 0.2})

    received, response = await _through(ParallelToolCallsMiddleware(parallel), request)

    assert received.model_settings == {"parallel_tool_calls": parallel, "temperature": 0.2}
    assert response is _ANSWER


async def test_the_request_it_was_handed_is_left_as_it_was() -> None:
    request = _request(tools=[ping])

    received, _ = await _through(ParallelToolCallsMiddleware(True), request)

    assert request.model_settings == {}
    assert received is not request


async def test_a_model_call_without_tools_is_not_given_the_setting() -> None:
    request = _request(tools=[])

    received, _ = await _through(ParallelToolCallsMiddleware(True), request)

    assert received is request
    assert received.model_settings == {}


async def test_a_setting_the_request_already_carries_is_kept() -> None:
    request = _request(tools=[ping], model_settings={"parallel_tool_calls": False})

    received, _ = await _through(ParallelToolCallsMiddleware(True), request)

    assert received.model_settings == {"parallel_tool_calls": False}


def _names(engine: EngineParams | None) -> list[str]:
    return [m.name for m in build_middlewares(create_registry(), [], engine)]


@pytest.mark.parametrize("engine", [None, EngineParams(), EngineParams(enable_parallel_tool_calls=None)])
def test_an_engine_that_leaves_the_switch_unset_has_no_such_middleware(engine: EngineParams | None) -> None:
    assert "ParallelToolCallsMiddleware" not in _names(engine)


@pytest.mark.parametrize("parallel", [True, False])
def test_the_middleware_goes_last_of_the_model_call_wrappers(parallel: bool) -> None:
    names = _names(EngineParams(enable_parallel_tool_calls=parallel))

    assert names[-3:] == ["stringified_json_args_middleware", "ParallelToolCallsMiddleware", "debug_logger_middleware"]


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    with shipped_session(tmp_path):
        yield


def _turns(*, with_tool_round: bool) -> list[AIMessage]:
    answer = AIMessage(content="done")
    if not with_tool_round:
        return [answer]
    return [AIMessage(content="", tool_calls=[{"id": "p1", "name": "ping", "args": {}}]), answer]


async def _bindings(engine: EngineParams | None, *, with_tool_round: bool) -> list[dict[str, object]]:
    model, agent = shipped_agent(_turns(with_tool_round=with_tool_round), [ping], engine=engine)
    await agent.ainvoke({"messages": [HumanMessage(content="go")]})
    return model.bindings


@pytest.mark.parametrize("parallel", [True, False])
async def test_every_model_call_of_the_shipped_graph_is_bound_with_the_setting(parallel: bool) -> None:
    bindings = await _bindings(EngineParams(enable_parallel_tool_calls=parallel), with_tool_round=True)

    assert len(bindings) == 2  # the turn that calls the tool, and the turn that answers after it
    assert [binding.get("parallel_tool_calls") for binding in bindings] == [parallel, parallel]


async def test_the_shipped_graph_binds_no_setting_when_the_engine_leaves_the_switch_unset() -> None:
    bindings = await _bindings(EngineParams(), with_tool_round=True)

    assert len(bindings) == 2
    assert all("parallel_tool_calls" not in binding for binding in bindings)


async def test_the_tool_list_the_model_is_bound_to_decides_whether_the_setting_is_sent() -> None:
    # No tools in the graph: the model call binds nothing through ``bind_tools``, so no setting can be refused by a provider.
    model, agent = shipped_agent(
        _turns(with_tool_round=False), [], engine=EngineParams(enable_parallel_tool_calls=True)
    )
    await agent.ainvoke({"messages": [HumanMessage(content="go")]})

    assert model.bindings == []
    assert cast(ScriptedModel, model).calls  # the model was still called
