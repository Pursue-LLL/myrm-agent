"""The recent actions the security reviewer is shown are the calls that ran or are being judged, not refused ones."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolCall, ToolMessage

from myrm_agent_harness.agent.middlewares.approval.evaluation.evaluator import _recent_tool_calls
from myrm_agent_harness.agent.middlewares.approval.refusal import DenialCause, refusal_answer
from myrm_agent_harness.agent.security.types import SecurityConfig


def _call(call_id: str, command: str) -> ToolCall:
    return ToolCall(type="tool_call", name="bash_code_execute_tool", args={"command": command}, id=call_id)


def _turn(call: ToolCall, answer: ToolMessage | None) -> list[BaseMessage]:
    return [AIMessage(content="", tool_calls=[call]), *([answer] if answer else [])]


def _commands(messages: list[BaseMessage], config: SecurityConfig | None = None) -> list[str]:
    calls = _recent_tool_calls(messages, config or SecurityConfig())
    return [str(call.args["command"]) for call in calls]


def test_a_call_that_ran_is_shown_to_the_reviewer() -> None:
    ran = _call("c1", "cat report.txt")
    ok = ToolMessage(content="data", name=ran["name"], tool_call_id="c1")

    assert _commands([HumanMessage(content="go"), *_turn(ran, ok)]) == ["cat report.txt"]


def test_a_call_that_failed_while_running_is_still_shown_to_the_reviewer() -> None:
    failed = _call("c1", "cat missing.txt")
    error = ToolMessage(content="not found", name=failed["name"], tool_call_id="c1", status="error")

    assert _commands(_turn(failed, error)) == ["cat missing.txt"]


def test_a_call_that_was_refused_never_ran_so_it_is_not_shown_as_an_action() -> None:
    refused = _call("c1", "cat ~/.ssh/id_rsa")

    for cause in DenialCause:
        answer = refusal_answer(refused, "Not run.", cause)
        assert _commands(_turn(refused, answer)) == [], cause


def test_the_calls_around_a_refused_one_keep_their_order() -> None:
    first, refused, last = _call("c1", "ls"), _call("c2", "rm -rf /"), _call("c3", "pwd")
    messages = [
        *_turn(first, ToolMessage(content="a", name=first["name"], tool_call_id="c1")),
        *_turn(refused, refusal_answer(refused, "Not run.", DenialCause.USER)),
        *_turn(last, None),
    ]

    assert _commands(messages) == ["ls", "pwd"]


def test_a_call_without_an_id_is_never_taken_for_a_refused_one() -> None:
    anonymous = ToolCall(type="tool_call", name="bash_code_execute_tool", args={"command": "ls"}, id=None)
    refused = _call("c1", "rm -rf /")
    messages = [
        *_turn(refused, refusal_answer(refused, "Not run.", DenialCause.POLICY)),
        *_turn(anonymous, None),
    ]

    assert _commands(messages) == ["ls"]


def test_the_reviewer_sees_no_history_when_auto_mode_is_off() -> None:
    ran = _call("c1", "ls")

    assert _commands(_turn(ran, None), SecurityConfig(auto_mode_enabled=False)) == []
