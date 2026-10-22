"""The model's hallucinated tool names are repaired before the graph dispatches them.

Measured on the A2A delegation Chrome E2E: the model emitted ``a2a_call_tool`` while the
registered name is ``a2a_call``. LangGraph resolves names against its own map, so the call
was rejected, the model retried with the same wrong name, the retry budget ran out and the
turn ended with an empty assistant message (the chat window stayed blank for 180s).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.middlewares.tooling.skill_attenuation_middleware import (
    SkillAttenuationMiddleware,
)


def _request_with_tools(*names: str) -> MagicMock:
    tools = []
    for name in names:
        tool = MagicMock()
        tool.name = name
        tools.append(tool)
    request = MagicMock()
    request.tools = tools
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


def test_hallucinated_suffix_is_repaired_before_dispatch() -> None:
    request = _request_with_tools("a2a_call", "a2a_orchestrate")
    response = _response_with_calls("a2a_call_tool")

    repaired = SkillAttenuationMiddleware._repair_tool_call_names(response, request)

    calls = repaired.result[0].tool_calls
    assert calls[0]["name"] == "a2a_call"
    # The arguments and the call id must survive the repair untouched.
    assert calls[0]["args"] == {"peer": "p", "prompt": "q"}
    assert calls[0]["id"] == "call_0"


def test_registered_names_are_left_alone() -> None:
    request = _request_with_tools("a2a_call")
    response = _response_with_calls("a2a_call")

    assert SkillAttenuationMiddleware._repair_tool_call_names(response, request) is response


def test_unknown_name_is_not_forced_onto_a_tool() -> None:
    request = _request_with_tools("a2a_call")
    response = _response_with_calls("launch_rocket_hyperdrive")

    assert SkillAttenuationMiddleware._repair_tool_call_names(response, request) is response


def test_no_bound_tools_leaves_the_response_alone() -> None:
    request = _request_with_tools()
    response = _response_with_calls("a2a_call_tool")

    assert SkillAttenuationMiddleware._repair_tool_call_names(response, request) is response
