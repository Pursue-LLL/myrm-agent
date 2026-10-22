"""A resume that never reached the graph hands its interrupt back to the user instead of stranding it."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.gateway import AgentGateway
from app.services.agent.stream_session.session_reservation import release_unstreamed_reservation

CHAT_ID = "chat-reservation-1"
_GATEWAY_PATH = "app.services.agent.stream_session.session_reservation.get_agent_gateway"


@pytest.fixture(autouse=True)
def _fresh_scheduler() -> Iterator[None]:
    ApprovalTimeoutScheduler._instance = None
    yield
    ApprovalTimeoutScheduler._instance = None


def _release(gateway: AgentGateway, *, was_resume: bool) -> None:
    with patch(_GATEWAY_PATH, return_value=gateway):
        release_unstreamed_reservation(CHAT_ID, was_resume=was_resume)


def _claimed_resume(*, reserved: bool) -> AgentGateway:
    """A resume that claimed the interrupt, with or without a leftover session reservation."""
    gateway = AgentGateway()
    if reserved:
        gateway.reserve_session(CHAT_ID, active_message_id="m1")
    assert ApprovalTimeoutScheduler.get().resolve_if_first(CHAT_ID) is True
    return gateway


def test_unstreamed_resume_releases_the_session_and_reopens_its_interrupt() -> None:
    gateway = _claimed_resume(reserved=True)

    _release(gateway, was_resume=True)

    assert not gateway.is_session_active(CHAT_ID)
    assert ApprovalTimeoutScheduler.get().resolve_if_first(CHAT_ID) is True


def test_unstreamed_plain_turn_releases_the_session_without_touching_the_scheduler() -> None:
    gateway = _claimed_resume(reserved=True)

    _release(gateway, was_resume=False)

    assert not gateway.is_session_active(CHAT_ID)
    assert ApprovalTimeoutScheduler.get().resolve_if_first(CHAT_ID) is False


def test_resume_without_a_leftover_reservation_keeps_its_interrupt_claimed() -> None:
    """The stream took the reservation over, so the graph consumed the resume and the answer stands."""
    gateway = _claimed_resume(reserved=False)

    _release(gateway, was_resume=True)

    assert ApprovalTimeoutScheduler.get().resolve_if_first(CHAT_ID) is False
