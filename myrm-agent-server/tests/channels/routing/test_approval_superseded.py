"""A turn that starts in the session an approval waits in ends that approval: the run behind it is gone.

Runs on the real ``AgentRouter``, ``SessionGate`` and ``ApprovalTimeoutScheduler`` with a scripted agent. What the
harness does with a session that has moved on (an answer to the suspended run reaches nobody) is covered where the
harness is: ``test_resume_addressing_rounds.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.channels.i18n import get_text
from app.channels.routing.router import AgentRouter
from app.channels.types import ApprovalExpiry, InboundMessage, ProgressUpdate, QuickReply, StreamingText, TopicContext
from tests.support.pending_approvals import inbound_message, router_with_agent, said_by

_CHAT_KEY = "telegram:c1"
_LONG = 60.0


@pytest.fixture(autouse=True)
def _scheduler() -> Iterator[ApprovalTimeoutScheduler]:
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.cancel_all()
    yield scheduler
    scheduler.cancel_all()


def _approval_card(expiry_seconds: float) -> ProgressUpdate:
    return ProgressUpdate(
        label="send_email needs approval",
        quick_replies=(QuickReply(label="Approve", text="/approve", required=True),),
        expiry=ApprovalExpiry(seconds=expiry_seconds, behavior="deny"),
    )


class _Agent:
    """The first plain turn stops at a tool approval (when ``asks``); every later plain turn answers; resumes are recorded."""

    def __init__(self, *, asks: bool = True, expiry_seconds: float = _LONG) -> None:
        self._asks = asks
        self._expiry_seconds = expiry_seconds
        self.calls: list[InboundMessage] = []
        self.asked = asyncio.Event()
        self.answered = asyncio.Event()

    async def execute_stream(self, msg: InboundMessage, user_id: str, **_: object) -> AsyncGenerator[object, None]:
        self.calls.append(msg)
        if msg.resume_value is not None:
            yield StreamingText(text="resumed")
            return
        if self._asks and not self.asked.is_set():
            yield StreamingText(text="checking")
            yield _approval_card(self._expiry_seconds)
            self.asked.set()
            return
        yield StreamingText(text="It goes to the company list.")
        self.answered.set()

    @property
    def resumes(self) -> list[InboundMessage]:
        return [call for call in self.calls if call.resume_value is not None]


async def _until(event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), timeout=5)


async def _asked_in(router: AgentRouter, agent: _Agent) -> None:
    """The chat's first turn runs and stops at the approval."""
    router._gate.submit(inbound_message("mail the weekly report to everyone"))
    await _until(agent.asked)
    assert _CHAT_KEY in router._pending_approvals


@pytest.mark.asyncio
async def test_a_follow_up_turn_ends_the_approval_card_timer_and_numeric_shortcut() -> None:
    agent = _Agent(expiry_seconds=0.2)
    router, bus = router_with_agent(agent)
    await _asked_in(router, agent)

    router._gate.submit(inbound_message("who exactly will it be sent to?"))
    await _until(agent.answered)

    assert _CHAT_KEY not in router._pending_approvals
    bus.edit_channel_message.assert_awaited_once_with(
        "telegram", "c1", "prompt-1", get_text(inbound_message(), "approval_superseded")
    )
    assert not router._has_pending_approval(inbound_message("1"))  # a bare 1 is the user's text again, not an approval

    await asyncio.sleep(0.5)  # well past the approval's time limit
    assert agent.resumes == []
    assert get_text(inbound_message(), "approval_timeout_denied") not in said_by(bus)


@pytest.mark.asyncio
async def test_a_late_answer_is_told_there_is_no_open_request_and_resumes_nothing() -> None:
    agent = _Agent()
    router, bus = router_with_agent(agent)
    await _asked_in(router, agent)
    router._gate.submit(inbound_message("who exactly will it be sent to?"))
    await _until(agent.answered)

    await router._handle_approval_command(inbound_message("/approve"), "allow_once")

    assert said_by(bus)[-1] == get_text(inbound_message(), "no_pending_approval")
    assert agent.resumes == []


@pytest.mark.asyncio
async def test_the_notice_is_sent_as_a_message_when_the_card_cannot_carry_it() -> None:
    agent = _Agent()
    router, bus = router_with_agent(agent)
    bus.edit_channel_message = AsyncMock(return_value=False)
    await _asked_in(router, agent)

    router._gate.submit(inbound_message("who exactly will it be sent to?"))
    await _until(agent.answered)

    assert get_text(inbound_message(), "approval_superseded") in said_by(bus)


@pytest.mark.asyncio
async def test_the_turn_still_runs_when_the_notice_cannot_be_delivered() -> None:
    agent = _Agent()
    router, bus = router_with_agent(agent)
    bus.edit_channel_message = AsyncMock(side_effect=ConnectionError("platform is down"))
    await _asked_in(router, agent)

    router._gate.submit(inbound_message("who exactly will it be sent to?"))
    await _until(agent.answered)

    assert _CHAT_KEY not in router._pending_approvals


@pytest.mark.asyncio
async def test_a_delegated_runs_approval_ends_the_same_way() -> None:
    """A delegated run asks in the chat it came from and resumes in that chat's session, so a turn there ends it too."""
    agent = _Agent(asks=False)
    router, bus = router_with_agent(agent)
    await router._hand_over_delegated_approval(inbound_message("/delegate mail the report"), _approval_card(_LONG))
    assert _CHAT_KEY in router._pending_approvals

    router._gate.submit(inbound_message("never mind, what time is it?"))
    await _until(agent.answered)

    assert _CHAT_KEY not in router._pending_approvals
    bus.edit_channel_message.assert_awaited_once_with(
        "telegram", "c1", "prompt-1", get_text(inbound_message(), "approval_superseded")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asked_by", "follow_up_by", "ends"),
    [
        (None, None, True),
        ("agent-x", "agent-x", True),
        (None, "agent-x", False),
        ("agent-x", None, False),
        ("agent-x", "agent-y", False),
    ],
)
async def test_only_a_turn_of_the_same_agents_session_ends_the_approval(
    asked_by: str | None, follow_up_by: str | None, ends: bool
) -> None:
    """The agent is part of the session key: another agent's turn in the chat does not touch this agent's run."""

    def topic_of(agent_id: str | None) -> TopicContext | None:
        return None if agent_id is None else TopicContext(topic_id="c1", agent_id=agent_id, enabled=True)

    agent = _Agent()
    router, bus = router_with_agent(agent)
    router._resolve_topic = AsyncMock(side_effect=[topic_of(asked_by), topic_of(follow_up_by)])  # type: ignore[method-assign]
    await _asked_in(router, agent)

    router._gate.submit(inbound_message("who exactly will it be sent to?"))
    await _until(agent.answered)

    assert (_CHAT_KEY not in router._pending_approvals) is ends
    assert bus.edit_channel_message.await_count == (1 if ends else 0)
    router._pending_approvals.clear()


@pytest.mark.asyncio
async def test_a_message_that_starts_no_turn_leaves_the_approval_open() -> None:
    """Only a turn that actually runs takes the suspended run away; a sender the router turns away does not."""
    agent = _Agent()
    router, bus = router_with_agent(agent)
    await _asked_in(router, agent)
    router._resolver = AsyncMock(resolve_dm_user=AsyncMock(return_value=None))

    router._gate.submit(inbound_message("who exactly will it be sent to?"))
    await asyncio.sleep(0.6)

    assert len(agent.calls) == 1
    assert _CHAT_KEY in router._pending_approvals
    bus.edit_channel_message.assert_not_awaited()
    router._pending_approvals.clear()


@pytest.mark.parametrize("locale", ["en", "ja", "zh-CN", "zh-TW"])
def test_the_notice_exists_in_every_language_the_approval_can_be_asked_in(locale: str) -> None:
    notice = get_text(inbound_message(locale=locale), "approval_superseded")

    assert notice != "approval_superseded"
    if locale != "en":
        assert notice != get_text(inbound_message(), "approval_superseded")
