"""A resumed run goes back to the channel session of the turn that asked.

The session key carries a reset epoch, so a key worked out when the answer arrives can name another chat than the one the
run belongs to. The approval card names the asking turn's session, the router keeps it with the open request, and the
message that resumes the run, whoever answered, carries it. Runs on the real ``AgentRouter``, ``SessionGate`` and
``ApprovalTimeoutScheduler`` with a scripted agent.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncGenerator, Iterator

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.channels.routing.pending_approvals import PendingApproval, answer_resume_message
from app.channels.types import (
    METADATA_RESUME_SESSION_KEY,
    ApprovalExpiry,
    InboundMessage,
    ProgressUpdate,
    QuickReply,
    StreamingText,
)
from tests.support.pending_approvals import inbound_message, router_with_agent

_ASKED_SESSION = "telegram:dm:u1:e=2026-10-26"
_LONG = 60.0
_SHORT = 0.05


@pytest.fixture(autouse=True)
def _scheduler() -> Iterator[ApprovalTimeoutScheduler]:
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.cancel_all()
    yield scheduler
    scheduler.cancel_all()


def _approval_card(expiry_seconds: float = _LONG, session_key: str = _ASKED_SESSION) -> ProgressUpdate:
    return ProgressUpdate(
        label="send_email needs approval",
        quick_replies=(QuickReply(label="Approve", text="/approve", required=True),),
        expiry=ApprovalExpiry(seconds=expiry_seconds, behavior="deny"),
        session_key=session_key,
    )


class _Agent:
    """The first plain turn stops at a tool approval, a resume finishes its run; the resume messages are kept."""

    def __init__(self, expiry_seconds: float = _LONG) -> None:
        self._expiry_seconds = expiry_seconds
        self.resumes: list[InboundMessage] = []
        self.asked = asyncio.Event()
        self.resumed = asyncio.Event()

    async def execute_stream(self, msg: InboundMessage, user_id: str, **kwargs: object) -> AsyncGenerator[object, None]:
        if msg.resume_value is not None:
            self.resumes.append(msg)
            yield StreamingText(text="mail sent")
            self.resumed.set()
            return
        yield StreamingText(text="checking")
        yield _approval_card(self._expiry_seconds)
        self.asked.set()


async def _until(event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), timeout=5)


@pytest.mark.asyncio
async def test_an_approved_run_resumes_in_the_session_of_the_turn_that_asked() -> None:
    agent = _Agent()
    router, _bus = router_with_agent(agent)

    router._gate.submit(inbound_message("mail the report"))
    await _until(agent.asked)
    await router._handle_approval_command(inbound_message("/approve"), "allow_once")
    await _until(agent.resumed)

    (resume,) = agent.resumes
    assert resume.metadata[METADATA_RESUME_SESSION_KEY] == _ASKED_SESSION


@pytest.mark.asyncio
async def test_an_unanswered_approval_resumes_in_the_session_of_the_turn_that_asked() -> None:
    agent = _Agent(expiry_seconds=_SHORT)
    router, _bus = router_with_agent(agent)

    router._gate.submit(inbound_message("mail the report"))
    await _until(agent.resumed)

    (resume,) = agent.resumes
    assert resume.metadata[METADATA_RESUME_SESSION_KEY] == _ASKED_SESSION


@pytest.mark.asyncio
async def test_an_approved_delegated_run_resumes_in_the_session_it_asked_in() -> None:
    agent = _Agent()
    router, _bus = router_with_agent(agent)
    await router._hand_over_delegated_approval(inbound_message("/delegate mail the report"), _approval_card())

    await router._handle_approval_command(inbound_message("/approve"), "allow_once")
    await _until(agent.resumed)

    (resume,) = agent.resumes
    assert resume.metadata[METADATA_RESUME_SESSION_KEY] == _ASKED_SESSION


def _asked(session_key: str) -> PendingApproval:
    return PendingApproval(
        card_message_id="card-1", message=inbound_message("mail the report"), user_id="u1", session_key=session_key
    )


def test_the_session_of_the_asking_turn_replaces_whatever_the_answer_carries() -> None:
    answer = dataclasses.replace(inbound_message("/approve"), metadata={METADATA_RESUME_SESSION_KEY: "telegram:dm:u2"})

    resume = answer_resume_message(answer, {"decisions": []}, _asked(_ASKED_SESSION))

    assert resume.metadata[METADATA_RESUME_SESSION_KEY] == _ASKED_SESSION


def test_a_request_that_named_no_session_resumes_without_one() -> None:
    resume = answer_resume_message(inbound_message("/approve"), {"decisions": []}, _asked(""))

    assert METADATA_RESUME_SESSION_KEY not in resume.metadata


@pytest.mark.parametrize("asked", [None, _asked("")], ids=["no-request-held", "request-named-no-session"])
def test_a_session_key_the_answer_carries_is_never_honoured(asked: PendingApproval | None) -> None:
    answer = dataclasses.replace(inbound_message("/approve"), metadata={METADATA_RESUME_SESSION_KEY: "telegram:dm:u2"})

    resume = answer_resume_message(answer, {"decisions": []}, asked)

    assert METADATA_RESUME_SESSION_KEY not in resume.metadata


def test_a_session_key_the_asking_message_carries_is_not_copied_into_the_timeout_resume() -> None:
    asking = dataclasses.replace(inbound_message("mail the report"), metadata={METADATA_RESUME_SESSION_KEY: "telegram:dm:u2"})
    asked = PendingApproval(card_message_id="card-1", message=asking, user_id="u1", session_key="")

    resume = asked.resume_message({"decisions": []})

    assert METADATA_RESUME_SESSION_KEY not in resume.metadata
