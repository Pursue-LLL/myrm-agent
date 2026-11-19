"""Which timer ``arm_interrupt_timeout`` arms and what each timer registers with the scheduler.

A stand-in scheduler records the registration; no agent run starts. The resume a fired timer runs is covered by
``test_hitl_timeout.py`` against the real scheduler.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.agent.streaming.interrupt_events import INTERRUPT_ID_KEY

from app.services.agent.streaming_support import hitl_timeout
from app.services.agent.streaming_support.hitl_timeout import (
    CLARIFICATION_TIMEOUT_SECONDS,
    arm_interrupt_timeout,
    schedule_approval_timeout,
    schedule_clarification_timeout,
)

CHAT_ID = "chat-hitl"
CARD_ID = "interrupt-card-1"


def _params() -> MagicMock:
    params = MagicMock()
    params.chat_id = CHAT_ID
    params.message_id = "msg-1"
    params.model_copy.return_value = params
    return params


@pytest.mark.parametrize(
    ("schedule", "seconds", "behavior", "override"),
    [
        (
            lambda params: schedule_clarification_timeout(CHAT_ID, params, CARD_ID),
            CLARIFICATION_TIMEOUT_SECONDS,
            "deny",
            {INTERRUPT_ID_KEY: CARD_ID},
        ),
        (
            lambda params: schedule_approval_timeout(CHAT_ID, {"seconds": "45", "behavior": "allow"}, params),
            45.0,
            "allow",
            None,
        ),
    ],
)
def test_each_kind_registers_its_timeout_decision(
    schedule: Callable[[MagicMock], None], seconds: float, behavior: str, override: dict[str, object] | None
) -> None:
    scheduler = MagicMock()
    with patch.object(ApprovalTimeoutScheduler, "get", return_value=scheduler):
        schedule(_params())

    kwargs = scheduler.schedule.call_args.kwargs
    assert kwargs["key"] == CHAT_ID
    assert kwargs["timeout_seconds"] == seconds
    assert kwargs["behavior"] == behavior
    assert kwargs["resume_value_override"] == override
    assert callable(kwargs["resume_callback"])


def test_constants_match_the_documented_timeouts() -> None:
    assert CLARIFICATION_TIMEOUT_SECONDS == 900.0


@pytest.mark.parametrize("seconds", [object(), None, "soon", float("inf")])
def test_unusable_approval_seconds_fall_back_to_the_default(seconds: object) -> None:
    scheduler = MagicMock()
    with patch.object(ApprovalTimeoutScheduler, "get", return_value=scheduler):
        schedule_approval_timeout(CHAT_ID, {"seconds": seconds, "behavior": "deny"}, _params())

    assert scheduler.schedule.call_args.kwargs["timeout_seconds"] == 300.0


@pytest.mark.parametrize(
    ("approval_timeout", "clarification_interrupt_id", "armed"),
    [
        ({"seconds": 1}, CARD_ID, "clarification"),
        ({"seconds": 5, "behavior": "deny"}, None, "approval"),
    ],
)
def test_arm_interrupt_timeout_picks_the_interrupt_that_carries_a_timer(
    approval_timeout: dict[str, object] | None,
    clarification_interrupt_id: str | None,
    armed: str,
) -> None:
    scheduler = MagicMock()
    with (
        patch.object(ApprovalTimeoutScheduler, "get", return_value=scheduler),
        patch.object(hitl_timeout, "schedule_clarification_timeout") as clarification,
        patch.object(hitl_timeout, "schedule_approval_timeout") as approval,
    ):
        arm_interrupt_timeout(
            CHAT_ID,
            _params(),
            approval_timeout=approval_timeout,
            clarification_interrupt_id=clarification_interrupt_id,
            awaiting_answer=True,
        )

    called = {name for name, mock in (("clarification", clarification), ("approval", approval)) if mock.called}
    assert called == {armed}
    scheduler.reopen.assert_not_called()


def test_a_clarification_timer_is_armed_for_the_card_it_names() -> None:
    params = _params()
    with (
        patch.object(ApprovalTimeoutScheduler, "get", return_value=MagicMock()),
        patch.object(hitl_timeout, "schedule_clarification_timeout") as clarification,
    ):
        arm_interrupt_timeout(CHAT_ID, params, approval_timeout=None, clarification_interrupt_id=CARD_ID, awaiting_answer=True)

    clarification.assert_called_once_with(CHAT_ID, params, CARD_ID)


@pytest.mark.parametrize(("awaiting_answer", "reopened"), [(True, True), (False, False)])
def test_arm_interrupt_timeout_reopens_only_an_interrupt_without_a_timer(awaiting_answer: bool, reopened: bool) -> None:
    scheduler = MagicMock()
    with patch.object(ApprovalTimeoutScheduler, "get", return_value=scheduler):
        arm_interrupt_timeout(
            CHAT_ID,
            _params(),
            approval_timeout=None,
            clarification_interrupt_id=None,
            awaiting_answer=awaiting_answer,
        )

    assert scheduler.reopen.called is reopened
