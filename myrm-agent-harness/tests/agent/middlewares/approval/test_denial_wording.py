"""How a refusal reads to the model: who refused, and what to do next."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.middlewares._session_context import set_approval_session
from myrm_agent_harness.agent.middlewares.approval._denial_wording import DenialCause, denial_hint, rejection_message
from myrm_agent_harness.agent.middlewares.approval.helpers import (
    clear_all_session_denials_for_tests,
    record_denial,
    record_rejection,
)

_POLICY_HINT = (
    "\n\n[System: This action was denied. "
    "Find a safer alternative approach to achieve the user's goal. "
    "Do NOT attempt to circumvent or route around the security block.]"
)


@pytest.fixture(autouse=True)
def _clean_denials() -> None:
    clear_all_session_denials_for_tests()
    set_approval_session("web-session")


def test_a_policy_denial_keeps_the_established_wording() -> None:
    assert denial_hint(DenialCause.POLICY, "none", 1, 3, unattended=False) == _POLICY_HINT


def test_the_cause_decides_who_the_model_is_told_refused() -> None:
    user = denial_hint(DenialCause.USER, "none", 1, 3, unattended=False)
    timeout = denial_hint(DenialCause.TIMEOUT, "none", 1, 3, unattended=False)

    assert "security block" not in user
    assert "The user declined" in user
    assert "did not answer in time" in timeout
    assert "declined" not in timeout


@pytest.mark.parametrize("cause", list(DenialCause))
def test_an_attended_session_past_a_threshold_hears_that_auto_mode_is_suspended(cause: DenialCause) -> None:
    consecutive = denial_hint(cause, "consecutive", 3, 3, unattended=False)
    total = denial_hint(cause, "total", 20, 20, unattended=False)

    assert consecutive == (
        "\n\n[System: 3 consecutive denials (threshold: 3). Auto-mode is being suspended — all subsequent actions "
        "will require explicit human approval. Stop and explain to the user what you were trying to do.]"
    )
    assert total == (
        "\n\n[System: 20 total denials in this session (threshold: 20). Auto-mode is being suspended — all "
        "subsequent actions will require explicit human approval. Explain to the user what happened and ask for "
        "guidance.]"
    )


@pytest.mark.parametrize("breach", ["consecutive", "total"])
def test_an_unattended_run_is_not_promised_a_human_and_is_told_to_report(breach: str) -> None:
    hint = denial_hint(DenialCause.POLICY, breach, 3, 3, unattended=True)

    assert "scheduled job" in hint
    assert "Do not retry" in hint
    assert "final reply" in hint
    assert "human approval" not in hint


def test_a_person_gives_a_reason_and_a_timer_gives_none() -> None:
    assert rejection_message("too risky", timed_out=False) == "Action rejected by user: too risky"
    assert "timed out" in rejection_message("Auto-rejected: approval timeout (300s)", timed_out=True)
    assert "Auto-rejected" not in rejection_message("Auto-rejected: approval timeout (300s)", timed_out=True)


def test_a_denial_is_worded_for_a_scheduled_job_by_its_session_key() -> None:
    for _ in range(2):
        record_denial("step", "cron:job-1")

    assert "scheduled job" in record_denial("step", "cron:job-1")


def test_a_denial_in_an_attended_session_escalates_with_the_attended_wording() -> None:
    for _ in range(2):
        record_denial("step", "web-1")

    assert "explicit human approval" in record_denial("step", "web-1")


def test_the_active_session_decides_when_no_key_is_given() -> None:
    set_approval_session("cron:job-9")
    for _ in range(2):
        record_denial("step")

    assert "scheduled job" in record_denial("step")


def test_a_rejection_returns_the_users_reason_and_counts_as_a_denial() -> None:
    feedback, text = record_rejection({"type": "reject", "feedback": "  not now  "}, "step", "web-1")

    assert feedback == "not now"
    assert text.startswith("Action rejected by user: not now")
    assert "The user declined" in text
    assert "3 consecutive denials" in record_denial("step", "web-1") + record_denial("step", "web-1")


def test_a_rejection_without_a_reason_says_so() -> None:
    feedback, text = record_rejection({"type": "reject"}, "step", "web-1")

    assert feedback == "User rejected this action."
    assert text.startswith("Action rejected by user: User rejected this action.")


def test_a_rejection_the_timer_resolved_is_worded_as_no_answer() -> None:
    _, text = record_rejection({"type": "reject", "feedback": "Auto-rejected", "timed_out": True}, "step", "web-1")

    assert "timed out" in text
    assert "did not answer in time" in text
    assert "rejected by user" not in text.lower()
