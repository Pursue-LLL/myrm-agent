"""The model's hallucinated tool names are repaired before the graph dispatches them.

Measured on the A2A delegation Chrome E2E: the model emitted ``a2a_call_tool`` while the
registered name is ``a2a_call``. LangGraph resolves names against its own map, so the call
was rejected ("not a valid tool"), the model retried with the same wrong name, the retry budget
ran out and the turn ended with an empty assistant message.

``request.tools`` is empty when the caller pre-binds the model, which is exactly the server's
case, so the repair must take the name set from the tool registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.middlewares.tooling.skill_attenuation_middleware import (
    SkillAttenuationMiddleware,
)


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


def _response_with_calls(*names: str) -> MagicMock:
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": {"peer": "p", "prompt": "q"}, "id": f"call_{index}"}
            for index, name in enumerate(names)
        ],
    )
    response = MagicMock()
    response.result = [message]
    response.model_copy.side_effect = lambda update: MagicMock(**update)
    return response


def test_hallucinated_suffix_is_repaired_from_the_registry() -> None:
    """The server pre-binds the model, so `request.tools` is empty — the registry decides."""
    middleware = _middleware("a2a_call", "a2a_orchestrate")
    response = _response_with_calls("a2a_call_tool")

    repaired = middleware._repair_tool_call_names(response, _request_with_tools())

    calls = repaired.result[0].tool_calls
    assert calls[0]["name"] == "a2a_call"
    # The arguments and the call id must survive the repair untouched.
    assert calls[0]["args"] == {"peer": "p", "prompt": "q"}
    assert calls[0]["id"] == "call_0"


def test_registered_names_are_left_alone() -> None:
    middleware = _middleware("a2a_call")
    response = _response_with_calls("a2a_call")

    assert middleware._repair_tool_call_names(response, _request_with_tools()) is response


def test_unknown_name_is_not_forced_onto_a_tool() -> None:
    middleware = _middleware("a2a_call")
    response = _response_with_calls("launch_rocket_hyperdrive")

    assert middleware._repair_tool_call_names(response, _request_with_tools()) is response


def test_an_empty_registry_leaves_the_response_alone() -> None:
    middleware = _middleware()
    response = _response_with_calls("a2a_call_tool")

    assert middleware._repair_tool_call_names(response, _request_with_tools()) is response
