"""The stored evaluation: what goes into the checkpoint comes back as the tuples the batch processor uses."""

from __future__ import annotations

import pytest
from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.middlewares.approval.evaluation import (
    ApprovalEvaluation,
    evaluation_matches,
    pending_calls,
    refused_calls,
)
from myrm_agent_harness.agent.middlewares.approval.evaluation.record import build_evaluation
from myrm_agent_harness.runtime.checkpointing.factory import PickleSerde

CALL_A = ToolCall(type="tool_call", name="bash_code_execute_tool", args={"command": "make"}, id="a")
CALL_B = ToolCall(type="tool_call", name="web_fetch", args={"url": "https://example.com"}, id="b")
CARD_EXTRAS = {
    "high_risk": True,
    "blast_radius": {"files": 3, "paths": ["/tmp/x"]},
    "ptc_annotations": {"readOnlyHint": False},
}


def _evaluation(message_id: str | None = "m1") -> ApprovalEvaluation:
    return build_evaluation(
        message_id,
        refused=[(1, CALL_B, "refused: rate limit")],
        pending=[(0, CALL_A, "shell_exec", "needs a person", CARD_EXTRAS)],
    )


def test_the_verdict_tuples_come_back_as_they_went_in() -> None:
    evaluation = _evaluation()

    assert refused_calls(evaluation) == [(1, CALL_B, "refused: rate limit")]
    assert pending_calls(evaluation) == [(0, CALL_A, "shell_exec", "needs a person", CARD_EXTRAS)]


def test_a_call_without_card_extras_stays_without_them() -> None:
    evaluation = build_evaluation("m1", refused=[], pending=[(0, CALL_A, "shell_exec", "why", None)])

    assert pending_calls(evaluation) == [(0, CALL_A, "shell_exec", "why", None)]


def test_the_evaluation_survives_the_checkpoint_serializer_the_product_uses() -> None:
    serde = PickleSerde()

    restored = serde.loads_typed(serde.dumps_typed(_evaluation()))

    assert restored == _evaluation()
    assert pending_calls(restored) == pending_calls(_evaluation())


@pytest.mark.parametrize(
    ("evaluation", "message_id", "matches"),
    [
        (_evaluation("m1"), "m1", True),
        (_evaluation("m1"), "m2", False),
        (_evaluation("m1"), None, False),
        (_evaluation(None), None, False),
        (None, "m1", False),
    ],
)
def test_an_evaluation_belongs_only_to_the_model_response_it_was_made_for(
    evaluation: ApprovalEvaluation | None, message_id: str | None, matches: bool
) -> None:
    assert evaluation_matches(evaluation, message_id) is matches
