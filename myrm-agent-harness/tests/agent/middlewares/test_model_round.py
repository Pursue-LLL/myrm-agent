"""The model round a tool call belongs to is the model response that issued it.

Calls one response issues run side by side and see the same state, so they must share one round id;
the next response, however it is identified, must not.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.middlewares.tooling._model_round import model_round_id


def _call(call_id: str) -> dict[str, object]:
    return {"name": "fetch", "args": {}, "id": call_id}


def _state(*messages: object) -> dict[str, object]:
    return {"messages": [HumanMessage("go"), *messages]}


def test_calls_issued_by_one_response_share_its_id() -> None:
    response = AIMessage(content="", id="resp_1", tool_calls=[_call("a"), _call("b"), _call("c")])
    state = _state(response)

    assert {model_round_id(state, call_id) for call_id in ("a", "b", "c")} == {"resp_1"}


def test_the_next_response_is_another_round() -> None:
    first = AIMessage(content="", id="resp_1", tool_calls=[_call("a")])
    second = AIMessage(content="", id="resp_2", tool_calls=[_call("b")])
    state = _state(first, ToolMessage("page", tool_call_id="a"), second)

    assert model_round_id(state, "a") == "resp_1"
    assert model_round_id(state, "b") == "resp_2"


def test_a_response_without_an_id_is_known_by_its_first_call() -> None:
    state = _state(AIMessage(content="", tool_calls=[_call("a"), _call("b")]))

    assert model_round_id(state, "a") == model_round_id(state, "b") == "a"


def test_a_call_no_response_issued_has_no_round() -> None:
    state = _state(AIMessage(content="", id="resp_1", tool_calls=[_call("a")]))

    assert model_round_id(state, "stranger") is None


def test_a_state_without_messages_has_no_round() -> None:
    assert model_round_id({}, "a") is None
    assert model_round_id({"messages": None}, "a") is None
    assert model_round_id(object(), "a") is None
