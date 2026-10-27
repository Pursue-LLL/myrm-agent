"""The router's registry of open tool approvals: one owner for the wait, the card and the timer.

Runs on the real ``ApprovalTimeoutScheduler`` (the claim shared with the manual answer); only the expiry report is
recorded. The claim key is chat-wide, so a manual answer after the timer fired must be told the wait already ended.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Literal

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.channels.routing.pending_approvals import METADATA_APPROVAL_TIMED_OUT_KEY, PendingApproval, PendingApprovals
from app.channels.types import ApprovalExpiry
from tests.support.pending_approvals import asked_in

_TIMER_SECONDS = 0.05
_CHAT_KEY = "telegram:c1"
_TIMED_OUT = {"decision": "reject", "feedback": "No response within the time limit", "timed_out": True}


@pytest.fixture(autouse=True)
def _scheduler() -> Iterator[ApprovalTimeoutScheduler]:
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.cancel_all()
    yield scheduler
    scheduler.cancel_all()


class _Expiries:
    """Records what the registry reports when a wait runs out."""

    def __init__(self, *, fail: bool = False) -> None:
        self.reports: list[tuple[str, str, dict[str, object]]] = []
        self.reported = asyncio.Event()
        self._fail = fail

    async def __call__(self, state_key: str, pending: PendingApproval, resume_value: dict[str, object]) -> None:
        self.reports.append((state_key, pending.card_message_id, resume_value))
        self.reported.set()
        if self._fail:
            raise RuntimeError("the chat could not be told")


async def _wait_for(expiries: _Expiries) -> None:
    await asyncio.wait_for(expiries.reported.wait(), timeout=2)


@pytest.mark.asyncio
async def test_a_wait_that_runs_out_is_reported_once_and_closed() -> None:
    expiries = _Expiries()
    registry = PendingApprovals(expiries)
    registry.register(_CHAT_KEY, asked_in(card_message_id="card-1"), ApprovalExpiry(seconds=_TIMER_SECONDS))

    assert registry.card_message_id(_CHAT_KEY) == "card-1"
    await _wait_for(expiries)

    ((state_key, card_id, resume_value),) = expiries.reports
    assert (state_key, card_id) == (_CHAT_KEY, "card-1")
    assert resume_value["decision"] == "reject" and resume_value["timed_out"] is True
    assert _CHAT_KEY not in registry


@pytest.mark.asyncio
@pytest.mark.parametrize(("behavior", "decision"), [("allow", "approve"), ("deny", "reject")])
async def test_the_report_carries_the_decision_the_request_set(behavior: Literal["allow", "deny"], decision: str) -> None:
    expiries = _Expiries()
    registry = PendingApprovals(expiries)
    registry.register(_CHAT_KEY, asked_in(), ApprovalExpiry(seconds=_TIMER_SECONDS, behavior=behavior))

    await _wait_for(expiries)

    assert expiries.reports[0][2]["decision"] == decision


@pytest.mark.asyncio
async def test_an_answer_ends_the_wait_and_its_timer(_scheduler: ApprovalTimeoutScheduler) -> None:
    expiries = _Expiries()
    registry = PendingApprovals(expiries)
    pending = asked_in()
    registry.register(_CHAT_KEY, pending, ApprovalExpiry(seconds=_TIMER_SECONDS))

    assert registry.pop(_CHAT_KEY) is pending
    await asyncio.sleep(_TIMER_SECONDS * 4)

    assert expiries.reports == []
    assert _scheduler.pending_count == 0
    assert registry.pop(_CHAT_KEY) is None


@pytest.mark.asyncio
async def test_a_request_without_a_time_limit_waits_for_an_answer_and_the_answer_is_accepted(
    _scheduler: ApprovalTimeoutScheduler,
) -> None:
    key = asked_in().timer_key
    assert _scheduler.resolve_if_first(key) is True  # an earlier answer of this chat left the claim taken
    registry = PendingApprovals(_Expiries())

    registry.register(_CHAT_KEY, asked_in(), None)

    assert _scheduler.pending_count == 0
    assert _scheduler.resolve_if_first(key) is True


@pytest.mark.asyncio
async def test_a_failed_report_gives_the_claim_back_so_the_chats_answer_is_accepted(
    _scheduler: ApprovalTimeoutScheduler,
) -> None:
    expiries = _Expiries(fail=True)
    registry = PendingApprovals(expiries)
    registry.register(_CHAT_KEY, asked_in(), ApprovalExpiry(seconds=_TIMER_SECONDS))

    await _wait_for(expiries)
    await asyncio.sleep(0)

    assert _scheduler.resolve_if_first(asked_in().timer_key) is True


@pytest.mark.asyncio
async def test_the_timer_that_claimed_the_request_refuses_a_late_manual_answer(_scheduler: ApprovalTimeoutScheduler) -> None:
    expiries = _Expiries()
    registry = PendingApprovals(expiries)
    registry.register(_CHAT_KEY, asked_in(), ApprovalExpiry(seconds=_TIMER_SECONDS))

    await _wait_for(expiries)

    assert _scheduler.resolve_if_first(asked_in().timer_key) is False


@pytest.mark.asyncio
async def test_a_later_request_of_the_chat_takes_over_the_timer(_scheduler: ApprovalTimeoutScheduler) -> None:
    """Two forum topics of one chat share the claim key: the later request owns the single timer."""
    expiries = _Expiries()
    registry = PendingApprovals(expiries)
    registry.register(f"{_CHAT_KEY}:t1", asked_in(thread_id="t1"), ApprovalExpiry(seconds=_TIMER_SECONDS))
    registry.register(f"{_CHAT_KEY}:t2", asked_in(thread_id="t2"), ApprovalExpiry(seconds=_TIMER_SECONDS))

    registry.pop(f"{_CHAT_KEY}:t1")
    assert _scheduler.pending_count == 1  # the timer is the later request's, which still waits

    registry.pop(f"{_CHAT_KEY}:t2")
    assert _scheduler.pending_count == 0


@pytest.mark.asyncio
async def test_clear_ends_every_wait_and_timer(_scheduler: ApprovalTimeoutScheduler) -> None:
    expiries = _Expiries()
    registry = PendingApprovals(expiries)
    registry.register(_CHAT_KEY, asked_in(), ApprovalExpiry(seconds=_TIMER_SECONDS))
    registry.register("telegram:c2", asked_in(chat_id="c2"), ApprovalExpiry(seconds=_TIMER_SECONDS))

    registry.clear()
    await asyncio.sleep(_TIMER_SECONDS * 4)

    assert expiries.reports == []
    assert _scheduler.pending_count == 0
    assert _CHAT_KEY not in registry


def test_a_chat_that_waits_on_nothing_has_no_card() -> None:
    registry = PendingApprovals(_Expiries())

    assert registry.card_message_id(_CHAT_KEY) is None
    assert _CHAT_KEY not in registry


class TestResumeMessage:
    def test_it_resumes_the_asking_run_as_the_same_sender_with_the_timeouts_answer(self) -> None:
        pending = asked_in(sender_id="u1", user_id="owner-1")

        resume = pending.resume_message(_TIMED_OUT)

        assert resume.resume_value == _TIMED_OUT
        assert resume.content == "" and resume.media == () and resume.context_messages == ()
        assert resume.message_id is None
        assert (resume.user_id, resume.sender_id, resume.chat_id) == ("owner-1", "u1", "c1")
        assert resume.metadata["is_resume"] is True
        assert resume.metadata[METADATA_APPROVAL_TIMED_OUT_KEY] is True
        assert resume.metadata["locale"] == "en"

    def test_session_state_of_the_asking_turn_does_not_outlive_it(self) -> None:
        pending = asked_in()
        pending.message.metadata.update({"yolo_state": (0.0, 60), "personality_style": "terse", "force_new_epoch": True})

        resume = pending.resume_message(_TIMED_OUT)

        assert {"yolo_state", "personality_style", "force_new_epoch"}.isdisjoint(resume.metadata)
        assert "yolo_state" in pending.message.metadata  # the asking message itself is left as it was

    def test_the_timer_key_is_the_chat_wide_key_even_inside_a_topic(self) -> None:
        assert asked_in(thread_id="t1").timer_key == asked_in().timer_key == _CHAT_KEY
