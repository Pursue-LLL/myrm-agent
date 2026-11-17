"""The model's hallucinated tool names are repaired before the graph dispatches them.

Measured on a live run: the model emitted ``todo_write_tool`` while the registered
name is ``todo_write``. LangGraph resolves names against its own map, so the call
was rejected ("not a valid tool"), the model retried with the same wrong name, the retry budget
ran out and the turn ended with an empty assistant message.

``request.tools`` is empty when the caller pre-binds the model, which is exactly the server's
case, so the repair must take the name set from the tool registry. The registry holds only what the
agent was given, so a name is never repaired to a built-in tool an agent run with ``no_builtin_tools``
was not offered.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolCall
from langchain_core.tools import tool

from myrm_agent_harness.agent.middlewares.tooling.skill_attenuation_middleware import (
    SkillAttenuationMiddleware,
)
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolSource


@dataclass
class _Snapshot:
    name: str


class _Registry:
    def __init__(self, names: tuple[str, ...]) -> None:
        self._names = names

    def snapshot(self) -> list[_Snapshot]:
        return [_Snapshot(name=name) for name in self._names]


def _middleware(*registry_names: str) -> SkillAttenuationMiddleware:
    return SkillAttenuationMiddleware(registry=_Registry(registry_names))  # type: ignore[arg-type]


def _request_with_tools(*names: str) -> MagicMock:
    request = MagicMock()
    request.tools = []
    for name in names:
        tool = MagicMock()
        tool.name = name
        request.tools.append(tool)
    return request


def _response_with_calls(*names: str) -> ModelResponse[object]:
    """What a model call returns: the real response type, not a stand-in that accepts any method."""
    message = AIMessage(
        content="",
        tool_calls=[{"name": name, "args": {"todos": []}, "id": f"call_{index}"} for index, name in enumerate(names)],
    )
    return ModelResponse(result=[message], structured_response={"kept": True})


def _tool_calls(response: ModelResponse[object]) -> list[ToolCall]:
    message = response.result[0]
    assert isinstance(message, AIMessage)
    return message.tool_calls


def test_hallucinated_suffix_is_repaired_from_the_registry() -> None:
    """The server pre-binds the model, so `request.tools` is empty — the registry decides."""
    middleware = _middleware("todo_write", "kanban_show")
    response = _response_with_calls("todo_write_tool")

    repaired = middleware._repair_tool_call_names(response, _request_with_tools())

    calls = _tool_calls(repaired)
    assert calls[0]["name"] == "todo_write"
    # The arguments and the call id must survive the repair untouched.
    assert calls[0]["args"] == {"todos": []}
    assert calls[0]["id"] == "call_0"
    assert repaired.structured_response == {"kept": True}


@pytest.mark.asyncio
async def test_a_model_call_returns_the_repaired_response_through_the_middleware() -> None:
    middleware = _middleware("todo_write")
    request = ModelRequest(model=MagicMock(), messages=[HumanMessage(content="plan it")])

    async def handler(_request: ModelRequest[None]) -> ModelResponse[object]:
        return _response_with_calls("todo_write_tool")

    response = await middleware.awrap_model_call(request, handler)

    assert _tool_calls(response)[0]["name"] == "todo_write"


def test_registered_names_are_left_alone() -> None:
    middleware = _middleware("todo_write")
    response = _response_with_calls("todo_write")

    assert middleware._repair_tool_call_names(response, _request_with_tools()) is response


def test_unknown_name_is_not_forced_onto_a_tool() -> None:
    middleware = _middleware("todo_write")
    response = _response_with_calls("launch_rocket_hyperdrive")

    assert middleware._repair_tool_call_names(response, _request_with_tools()) is response


def test_an_empty_registry_leaves_the_response_alone() -> None:
    middleware = _middleware()
    response = _response_with_calls("todo_write_tool")

    assert middleware._repair_tool_call_names(response, _request_with_tools()) is response


@tool("skill_search_tool")
def _built_in_skill_search(query: str) -> str:
    """Built-in meta tool whose name a model can mistype."""
    return "hit"


@tool("calendar_lookup")
def _host_calendar_lookup(query: str) -> str:
    """Tool the host passes in."""
    return "event"


@pytest.mark.parametrize(
    ("no_builtin_tools", "repaired_name"),
    [(False, "skill_search_tool"), (True, "skill_searchtool")],
)
def test_a_mistyped_name_is_repaired_only_to_a_tool_the_agent_has(no_builtin_tools: bool, repaired_name: str) -> None:
    """An agent run without the built-in tools has none to repair a name to, so the call stays unrepaired."""
    registry = ToolRegistry(no_builtin_tools=no_builtin_tools)
    registry.register(_built_in_skill_search, source=ToolSource.META)
    registry.register(_host_calendar_lookup, source=ToolSource.USER)
    middleware = SkillAttenuationMiddleware(registry=registry)

    repaired = middleware._repair_tool_call_names(_response_with_calls("skill_searchtool"), _request_with_tools())

    assert _tool_calls(repaired)[0]["name"] == repaired_name
