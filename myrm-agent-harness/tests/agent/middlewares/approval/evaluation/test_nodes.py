"""The two approval nodes: the evaluation node stores verdicts, the approval node reads them and never judges again."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent.middlewares.approval import (
    ApprovalEvaluationMiddleware,
    ToolApprovalMiddleware,
    get_approval_rate_limiter,
    reset_denial_counter,
    set_approval_session,
    set_approval_user_id,
    set_security_config,
    set_workspace_root,
)
from myrm_agent_harness.agent.middlewares.approval.evaluation import (
    APPROVAL_EVALUATION_KEY,
    ApprovalEvaluation,
    pending_calls,
    refused_calls,
)
from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker
from myrm_agent_harness.agent.security.types import PermissionAction, PermissionRule, SecurityConfig

ASKING_CALL = ToolCall(
    type="tool_call", name="bash_code_execute_tool", args={"command": "python3 setup.py install"}, id="ask"
)
SAFE_CALL = ToolCall(type="tool_call", name="read_file", args={"path": "a.txt"}, id="safe")


class _Runtime:
    """The runtime handed to a hook; nothing in these tests reads it."""


@pytest.fixture(autouse=True)
def _session() -> Iterator[None]:
    approval_flow._allowlist = approval_flow.Allowlist()
    reset_taint_tracker()
    reset_denial_counter()
    get_approval_rate_limiter().reset(None)
    set_security_config(
        SecurityConfig(
            ruleset=(
                PermissionRule("*", "*", PermissionAction.ALLOW),
                PermissionRule("code_interpreter", "*", PermissionAction.ASK),
            )
        )
    )
    set_workspace_root("/tmp")
    set_approval_session("nodes")
    set_approval_user_id("")
    yield
    set_security_config(None)
    set_workspace_root("")
    set_approval_session("")
    set_approval_user_id("")


def _state(*calls: ToolCall, stored: ApprovalEvaluation | None = None, message_id: str = "m1") -> dict[str, object]:
    state: dict[str, object] = {
        "messages": [HumanMessage(content="go"), AIMessage(content="", id=message_id, tool_calls=list(calls))]
    }
    if stored is not None:
        state[APPROVAL_EVALUATION_KEY] = stored
    return state


async def _evaluate(*calls: ToolCall, message_id: str = "m1") -> ApprovalEvaluation:
    update = await ApprovalEvaluationMiddleware().aafter_model(_state(*calls, message_id=message_id), _Runtime())
    assert update is not None
    return update[APPROVAL_EVALUATION_KEY]


async def test_the_evaluation_node_stores_who_waits_and_names_the_model_response() -> None:
    evaluation = await _evaluate(ASKING_CALL, SAFE_CALL, message_id="m7")

    assert evaluation["message_id"] == "m7"
    assert [call["id"] for _, call, *_ in pending_calls(evaluation)] == ["ask"]
    assert refused_calls(evaluation) == []


async def test_the_evaluation_node_stores_nothing_for_a_response_without_tool_calls() -> None:
    state = {"messages": [AIMessage(content="just text", id="m1")]}

    assert await ApprovalEvaluationMiddleware().aafter_model(state, _Runtime()) is None


async def test_the_evaluation_node_stores_nothing_when_a_guard_already_answered_every_call() -> None:
    state = _state(ASKING_CALL)
    state["messages"].append(ToolMessage(content="held back", tool_call_id="ask", status="error"))  # type: ignore[attr-defined]

    assert await ApprovalEvaluationMiddleware().aafter_model(state, _Runtime()) is None


async def test_the_evaluation_node_refuses_the_calls_that_would_wait_when_the_user_asked_too_often() -> None:
    set_approval_user_id("busy-user")
    limiter = get_approval_rate_limiter()
    while limiter.check_limit("busy-user"):
        pass

    evaluation = await _evaluate(ASKING_CALL)

    assert pending_calls(evaluation) == []
    assert [(call["id"], "Rate limit" in text) for _, call, text in refused_calls(evaluation)] == [("ask", True)]


async def test_the_approval_node_reads_the_stored_verdicts_and_never_judges_the_calls_again(monkeypatch) -> None:
    stored = await _evaluate(ASKING_CALL)

    async def _must_not_judge(*args: object, **kwargs: object) -> ApprovalEvaluation:
        raise AssertionError("the approval node judged a call that was already judged")

    asked: list[object] = []

    def _answer(payload: object) -> dict[str, object]:
        asked.append(payload)
        return {"decisions": [{"type": "approve"}]}

    monkeypatch.setattr("myrm_agent_harness.agent.middlewares.approval.middleware.evaluate_target", _must_not_judge)
    monkeypatch.setattr("myrm_agent_harness.agent.middlewares.approval.middleware.interrupt", _answer)

    update = await ToolApprovalMiddleware().aafter_model(_state(ASKING_CALL, stored=stored), _Runtime())

    assert len(asked) == 1
    assert update is not None
    assert update[APPROVAL_EVALUATION_KEY] is None
    assert [call["id"] for call in update["messages"][0].tool_calls] == ["ask"]


async def test_the_approval_node_judges_the_calls_itself_when_the_stored_verdicts_are_for_another_response(
    monkeypatch, caplog
) -> None:
    other = await _evaluate(ASKING_CALL, message_id="older")
    asked: list[object] = []

    def _answer(payload: object) -> dict[str, object]:
        asked.append(payload)
        return {"decisions": [{"type": "approve"}]}

    monkeypatch.setattr("myrm_agent_harness.agent.middlewares.approval.middleware.interrupt", _answer)

    with caplog.at_level("WARNING"):
        update = await ToolApprovalMiddleware().aafter_model(
            _state(ASKING_CALL, stored=other, message_id="m1"), _Runtime()
        )

    assert len(asked) == 1
    assert "No stored evaluation" in caplog.text
    assert update is not None
    assert update[APPROVAL_EVALUATION_KEY] is None


async def test_the_approval_node_clears_verdicts_left_over_from_an_earlier_response() -> None:
    other = await _evaluate(ASKING_CALL, message_id="older")
    state: dict[str, object] = {"messages": [AIMessage(content="no calls", id="m2")], APPROVAL_EVALUATION_KEY: other}

    assert await ToolApprovalMiddleware().aafter_model(state, _Runtime()) == {APPROVAL_EVALUATION_KEY: None}


async def test_the_approval_node_answers_the_refused_calls_without_asking_anyone(monkeypatch) -> None:
    set_approval_user_id("busy-user")
    limiter = get_approval_rate_limiter()
    while limiter.check_limit("busy-user"):
        pass
    stored = await _evaluate(ASKING_CALL)

    def _must_not_ask(payload: object) -> dict[str, object]:
        raise AssertionError("a refused call was put to the user")

    monkeypatch.setattr("myrm_agent_harness.agent.middlewares.approval.middleware.interrupt", _must_not_ask)

    update = await ToolApprovalMiddleware().aafter_model(_state(ASKING_CALL, stored=stored), _Runtime())

    assert update is not None
    answers = [m for m in update["messages"] if isinstance(m, ToolMessage)]
    assert [(m.tool_call_id, m.status) for m in answers] == [("ask", "error")]
    assert update[APPROVAL_EVALUATION_KEY] is None
