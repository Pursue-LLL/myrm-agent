"""A kanban run that stops on a card holding a call only the user may answer says so in the reason its task is blocked with.

[INPUT]
- app.services.kanban.task_runner.stream::_StreamAccumulator (POS: reads the stop and its reason off the stream events)
- app.services.kanban.task_runner.outcomes::APPROVAL_NEEDED_BLOCK_REASON, PERSON_APPROVAL_NEEDED_BLOCK_REASON, TAKEOVER_NEEDED_BLOCK_REASON (POS: the fixed reasons a stop can carry)
- tests.support.kanban_run_pauses (POS: the pause events, built with the real harness payload builder)

[OUTPUT]
Pins which cards name the user-only reason: every kind of call the harness holds for a person (a write to a git hook or
an instruction file, a call that cannot be undone), alone or among ordinary calls; an ordinary card keeps the policy
reason. As for any request, the first one of a run names the reason and a run error outranks it.

[POS]
tests/services/kanban/test_task_runner_held_stop.py
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.agent.security.approval_reason import ApprovalReasonCode, CodedReason

from app.services.kanban.task_runner.outcomes import (
    APPROVAL_NEEDED_BLOCK_REASON,
    PERSON_APPROVAL_NEEDED_BLOCK_REASON,
    TAKEOVER_NEEDED_BLOCK_REASON,
)
from app.services.kanban.task_runner.stream import _StreamAccumulator
from tests.support.kanban_run_pauses import (
    BROWSER_TAKEOVER,
    HELD_APPROVAL,
    HELD_CALL,
    MIXED_APPROVAL,
    SHELL_CALL,
    TOOL_APPROVAL,
    PendingCall,
    approval_pause,
)

_INSTRUCTION_WRITE = CodedReason(
    "Protected instruction file write requires human approval: AGENTS.md",
    ApprovalReasonCode.PROTECTED_INSTRUCTION_WRITE,
    "AGENTS.md",
)
# What holds a call for the user: a write only a person may answer (named by its code), or a call that cannot be undone.
HELD_CALLS = [
    pytest.param(HELD_CALL, id="git-hook-write"),
    pytest.param((SHELL_CALL, "file_write", _INSTRUCTION_WRITE, None), id="instruction-file-write"),
    pytest.param((SHELL_CALL, "shell_exec", "requires approval", {"irreversible_destructive": True}), id="destructive"),
    pytest.param((SHELL_CALL, "shell_exec", "requires approval", {"socially_irreversible": True}), id="social"),
]
RUN_ERROR: dict[str, object] = {"type": "error", "error": "provider down", "error_type": "LLMError"}


def _fed(*events: dict[str, object]) -> _StreamAccumulator:
    acc = _StreamAccumulator()
    for event in events:
        acc.add(event)
    return acc


class TestTheReasonOfAHeldCard:
    @pytest.mark.parametrize("call", HELD_CALLS)
    def test_a_card_holding_a_call_only_the_user_may_answer_names_the_user_only_reason(self, call: PendingCall) -> None:
        assert _fed(approval_pause(call)).unanswered_request_reason == PERSON_APPROVAL_NEEDED_BLOCK_REASON

    def test_one_such_call_among_ordinary_ones_holds_the_whole_card(self) -> None:
        assert _fed(MIXED_APPROVAL).unanswered_request_reason == PERSON_APPROVAL_NEEDED_BLOCK_REASON

    def test_an_ordinary_card_keeps_the_policy_reason(self) -> None:
        assert _fed(TOOL_APPROVAL).unanswered_request_reason == APPROVAL_NEEDED_BLOCK_REASON

    @pytest.mark.parametrize(
        ("events", "reason"),
        [
            ((TOOL_APPROVAL, HELD_APPROVAL), APPROVAL_NEEDED_BLOCK_REASON),
            ((HELD_APPROVAL, TOOL_APPROVAL), PERSON_APPROVAL_NEEDED_BLOCK_REASON),
            ((BROWSER_TAKEOVER, HELD_APPROVAL), TAKEOVER_NEEDED_BLOCK_REASON),
            ((HELD_APPROVAL, BROWSER_TAKEOVER), PERSON_APPROVAL_NEEDED_BLOCK_REASON),
        ],
    )
    def test_the_first_request_names_the_reason(self, events: tuple[dict[str, object], ...], reason: str) -> None:
        assert _fed(*events).unanswered_request_reason == reason

    @pytest.mark.parametrize("events", [(HELD_APPROVAL, RUN_ERROR), (RUN_ERROR, HELD_APPROVAL)])
    def test_a_run_error_outranks_it(self, events: tuple[dict[str, object], ...]) -> None:
        assert _fed(*events).unanswered_request_reason is None
