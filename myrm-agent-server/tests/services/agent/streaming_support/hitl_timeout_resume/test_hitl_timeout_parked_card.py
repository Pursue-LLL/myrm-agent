"""A timer that answers a tool-approval card takes the card away from the parked run and ends the turn with it.

The resume a fired timer runs registers no collector of its own, so the parked run stays the chat's collector for the whole
resumed run. A page that reloads in that time must not get a card back that the timer already answered, and neither the parked
run nor the run digest may outlive the turn they were opened for.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

from app.services.agent.streaming_support import hitl_timeout
from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector
from app.services.copilot.run_digest_store import RunDigestStore
from tests.support.hitl_timeout_run import (
    CHAT_ID,
    card_collector,
    digest_phase,
    granted_lease,
    interrupted_lease,
    params_of_the_card,
    refused_lease,
    stopped_lease,
)


@pytest.mark.asyncio
async def test_the_card_is_gone_from_the_parked_run_while_the_timer_run_works(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert resumed_run == [False]
    assert parked.has_pending_tool_approval() is False


@pytest.mark.asyncio
async def test_the_parked_run_leaves_the_registry_when_the_timer_run_finishes(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    """Left registered, it would keep a reloading page attached to a stream that never ends."""
    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert ACTIVE_COLLECTORS.get(CHAT_ID) is None


@pytest.mark.asyncio
async def test_the_run_digest_ends_when_the_timer_run_finishes(parked: StreamContentCollector, resumed_run: list[bool]) -> None:
    """Left open, the digest keeps showing a run that is over until the chat's next run."""
    assert digest_phase() is RunDigestPhase.RUNNING
    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert digest_phase() is RunDigestPhase.COMPLETED


@pytest.mark.asyncio
async def test_the_parked_run_stays_registered_when_the_timer_run_stops_at_another_card(
    parked: StreamContentCollector, resumed_run: list[bool], stops_at_a_card: list[bool]
) -> None:
    stops_at_a_card.append(True)
    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert ACTIVE_COLLECTORS.get(CHAT_ID) is parked
    assert digest_phase() is RunDigestPhase.RUNNING


@pytest.mark.asyncio
async def test_a_newer_run_of_the_chat_keeps_its_registration(parked: StreamContentCollector, resumed_run: list[bool]) -> None:
    """A run the user started meanwhile owns the registry entry; the timer run's end must not remove it."""
    newer: list[StreamContentCollector] = []

    async def stream(**_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        newer.append(StreamContentCollector(chat_id=CHAT_ID))
        yield {"type": "message", "data": "continued"}

    with (
        patch("app.services.agent.streaming.ai_agent_service_stream", new=stream),
        patch.object(hitl_timeout, "server_turn_lease", granted_lease),
    ):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    try:
        assert ACTIVE_COLLECTORS.get(CHAT_ID) is newer[0]
    finally:
        newer[0].cleanup()


def _stream_that_raises(error: BaseException) -> Callable[..., AsyncGenerator[dict[str, object], None]]:
    async def stream(**_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        raise error
        yield {}  # pragma: no cover - makes this a generator

    return stream


@pytest.mark.asyncio
async def test_a_failed_timer_run_hands_the_card_back_so_a_manual_answer_still_has_one(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    """The failed run did not consume the answer: the scheduler is reopened for a manual one, which needs the card on the page."""
    scheduler = ApprovalTimeoutScheduler.get()
    with (
        patch("app.services.agent.streaming.ai_agent_service_stream", new=_stream_that_raises(RuntimeError("boom"))),
        patch.object(hitl_timeout, "server_turn_lease", granted_lease),
        patch.object(scheduler, "reopen") as reopen,
        pytest.raises(RuntimeError, match="boom"),
    ):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    reopen.assert_called_once_with(CHAT_ID)
    assert parked.has_pending_tool_approval() is True
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is parked
    assert digest_phase() is RunDigestPhase.RUNNING


@pytest.mark.asyncio
async def test_a_stopped_timer_run_ends_the_parked_run_too(parked: StreamContentCollector, resumed_run: list[bool]) -> None:
    """The user's Stop (or an E-Stop) cancels the timer run: the turn is over, whatever the stream was doing."""
    with (
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            new=_stream_that_raises(asyncio.CancelledError()),
        ),
        patch.object(hitl_timeout, "server_turn_lease", granted_lease),
        pytest.raises(asyncio.CancelledError),
    ):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert ACTIVE_COLLECTORS.get(CHAT_ID) is None
    assert digest_phase() is RunDigestPhase.CANCELLED


@pytest.mark.asyncio
async def test_the_run_digest_records_a_timer_run_the_user_stopped(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    with patch.object(hitl_timeout, "server_turn_lease", stopped_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert digest_phase() is RunDigestPhase.CANCELLED
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is None


@pytest.mark.asyncio
async def test_a_timer_task_cancelled_before_it_holds_the_chat_ends_nothing(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    with patch.object(hitl_timeout, "server_turn_lease", interrupted_lease), pytest.raises(asyncio.CancelledError):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert ACTIVE_COLLECTORS.get(CHAT_ID) is parked
    assert parked.has_pending_tool_approval() is True
    assert digest_phase() is RunDigestPhase.RUNNING


@pytest.mark.asyncio
async def test_the_card_stays_when_a_live_run_holds_the_chat(parked: StreamContentCollector, resumed_run: list[bool]) -> None:
    """The refused timer run answered nothing: the live run owns the suspended graph and the card with it."""
    with patch.object(hitl_timeout, "server_turn_lease", refused_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert resumed_run == []
    assert parked.has_pending_tool_approval() is True
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is parked
    assert digest_phase() is RunDigestPhase.RUNNING


@pytest.mark.asyncio
async def test_the_card_of_another_chat_is_left_alone(parked: StreamContentCollector, resumed_run: list[bool]) -> None:
    other = card_collector("chat-other")
    try:
        with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
            await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

        assert other.has_pending_tool_approval() is True
    finally:
        other.cleanup()


def test_a_failed_later_run_does_not_hand_back_a_card_an_earlier_run_answered(parked: StreamContentCollector) -> None:
    """Chained timers: the parked run settles once per answered card, and only the latest answer can be handed back."""
    parked.settle_tool_approvals()
    parked.settle_tool_approvals()

    parked.unsettle_tool_approvals()

    assert parked.has_pending_tool_approval() is False


@pytest.mark.asyncio
async def test_a_clarification_timer_marks_the_card_answered_and_ends_the_parked_turn(resumed_run: list[bool]) -> None:
    """The clarification card is stored with the message, so the timer flips it there; the parked run still leaves with the turn."""
    RunDigestStore.begin_run(CHAT_ID)
    parked_clarification = StreamContentCollector(chat_id=CHAT_ID)
    parked_clarification.feed_event({"type": "clarification_required", "messageId": "msg-1", "data": {}})
    mark_answered = AsyncMock()
    try:
        with (
            patch.object(hitl_timeout, "server_turn_lease", granted_lease),
            patch.object(hitl_timeout, "mark_pending_clarification_answered", new=mark_answered),
        ):
            await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {}, "clarification")

        mark_answered.assert_awaited_once_with(CHAT_ID, {"by": "timeout", "value": {}})
        assert ACTIVE_COLLECTORS.get(CHAT_ID) is None
        assert digest_phase() is RunDigestPhase.COMPLETED
    finally:
        parked_clarification.cleanup()
        RunDigestStore.clear(CHAT_ID)


@pytest.mark.asyncio
async def test_an_approval_timer_leaves_the_stored_clarification_card_alone(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    """Only a clarification timer answers the stored clarification card; a tool-approval timer must not flip it."""
    mark_answered = AsyncMock()
    with (
        patch.object(hitl_timeout, "server_turn_lease", granted_lease),
        patch.object(hitl_timeout, "mark_pending_clarification_answered", new=mark_answered),
    ):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    mark_answered.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_timer_run_without_a_parked_run_ends_cleanly(resumed_run: list[bool]) -> None:
    """The parked run is gone (its chat was cleaned up meanwhile): the timer run still answers and ends its digest."""
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is None
    try:
        with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
            await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

        assert resumed_run == [False]
        assert digest_phase() is RunDigestPhase.COMPLETED
    finally:
        RunDigestStore.clear(CHAT_ID)
