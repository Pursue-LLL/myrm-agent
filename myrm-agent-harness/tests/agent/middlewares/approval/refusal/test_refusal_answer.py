"""The result that answers a refused call names who refused it, so nothing downstream guesses."""

from __future__ import annotations

import pytest
from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.errors.fault_side import FaultSide, classify_tool_fault_side
from myrm_agent_harness.agent.middlewares.approval.refusal import DenialCause, refusal_answer, rejection_cause
from myrm_agent_harness.utils.errors import ToolErrorCategory

_CALL = ToolCall(type="tool_call", name="step", args={"text": "a"}, id="call-1")


@pytest.mark.parametrize(
    ("cause", "category"),
    [
        (DenialCause.POLICY, ToolErrorCategory.POLICY_DENIED),
        (DenialCause.USER, ToolErrorCategory.USER_DECLINED),
        (DenialCause.TIMEOUT, ToolErrorCategory.APPROVAL_TIMEOUT),
    ],
)
def test_the_answer_to_a_refused_call_carries_the_category_of_whoever_refused(
    cause: DenialCause, category: ToolErrorCategory
) -> None:
    answer = refusal_answer(_CALL, "Not run.", cause)

    assert answer.content == "Not run."
    assert answer.name == "step"
    assert answer.tool_call_id == "call-1"
    assert answer.status == "error"
    assert answer.additional_kwargs["error_category"] == category.value
    assert type(answer.additional_kwargs["error_category"]) is str


def test_a_call_without_a_name_or_an_id_is_still_answered() -> None:
    answer = refusal_answer(ToolCall(type="tool_call", name="", args={}, id=None), "Not run.", DenialCause.POLICY)

    assert answer.tool_call_id == ""
    assert answer.status == "error"


@pytest.mark.parametrize(
    ("decision", "cause"),
    [
        ({"type": "reject", "feedback": "no"}, DenialCause.USER),
        ({"type": "reject"}, DenialCause.USER),
        ({"decision": "reject", "timed_out": False}, DenialCause.USER),
        ({"decision": "reject", "feedback": "Auto-rejected", "timed_out": True}, DenialCause.TIMEOUT),
    ],
)
def test_only_the_approval_timer_resolves_a_decision_as_timed_out(
    decision: dict[str, object], cause: DenialCause
) -> None:
    assert rejection_cause(decision) is cause


def test_a_policy_refusal_is_the_owners_and_one_by_a_person_or_the_timer_names_no_side() -> None:
    assert classify_tool_fault_side(ToolErrorCategory.POLICY_DENIED.value) is FaultSide.OWNER
    assert classify_tool_fault_side(ToolErrorCategory.USER_DECLINED.value) is FaultSide.UNKNOWN
    assert classify_tool_fault_side(ToolErrorCategory.APPROVAL_TIMEOUT.value) is FaultSide.UNKNOWN
