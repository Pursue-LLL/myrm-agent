"""Every refusal text the approval flow produces cuts back to the line a person should read."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.middlewares.approval.denial_diagnostic_bridge import build_auto_review_denial_message
from myrm_agent_harness.agent.middlewares.approval.refusal import DenialCause, denial_hint, rejection_message
from myrm_agent_harness.core.security.model_directed_notes import user_facing_text


@pytest.mark.parametrize("cause", list(DenialCause))
@pytest.mark.parametrize(("breach", "count"), [("none", 1), ("consecutive", 3), ("total", 7)])
@pytest.mark.parametrize("unattended", [False, True])
def test_every_hint_is_cut_from_a_person_refusal(cause: DenialCause, breach: str, count: int, unattended: bool) -> None:
    refusal = rejection_message("use a dry run", timed_out=cause is DenialCause.TIMEOUT)
    hint = denial_hint(cause, breach, count, 3, unattended=unattended)

    assert hint, "a refusal always carries a note for the model"
    assert user_facing_text(refusal + hint) == refusal


@pytest.mark.parametrize("cause", [None, *DenialCause])
def test_a_policy_denial_with_its_diagnostic_is_cut_to_the_reason(cause: DenialCause | None) -> None:
    hint = "" if cause is None else denial_hint(cause, "none", 0, 3, unattended=False)

    message = build_auto_review_denial_message("bash_code_execute_tool", "rm -rf is not allowed", hint)

    assert "Diagnostic ID" in message and "Instruction:" in message
    assert user_facing_text(message) == "Tool execution denied by security policy: rm -rf is not allowed"
