"""Retiring the card a chat is parked at: no timer fires for it, the registry forgets it, and a late answer is refused.

The conversation moved on (the chat was deleted, cleared or rewritten, or the user sent a message instead of answering), so the
suspended graph is not the chat's any more. A timer that survived would resume a conversation nobody is in.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.streaming_support.stream_collector import (
    ACTIVE_COLLECTORS,
    StreamContentCollector,
    release_parked_hitl,
)
from tests.support.hitl_timeout_run import CHAT_ID

FAST = 0.05
PAUSES = {
    "clarification": {"type": "clarification_required", "messageId": "msg-1", "data": {}},
    "tool approval": {"type": "tool_approval_request", "messageId": "msg-1", "data": {"actionRequests": []}},
    "approval": {"type": "approval_required", "messageId": "msg-1", "data": {}},
}


def _parked_at(chat_id: str, pause: str) -> StreamContentCollector:
    collector = StreamContentCollector(chat_id=chat_id)
    collector.feed_event(PAUSES[pause])
    assert collector.has_pending_hitl_replay() is True
    return collector


async def _wait_past_the_timer() -> None:
    await asyncio.sleep(FAST * 4)


@pytest.mark.asyncio
@pytest.mark.parametrize("pause", list(PAUSES))
async def test_the_timer_of_a_retired_pause_never_fires(pause: str) -> None:
    fired = AsyncMock()
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.schedule(CHAT_ID, FAST, "deny", fired)
    parked = _parked_at(CHAT_ID, pause)
    try:
        release_parked_hitl(CHAT_ID)
        await _wait_past_the_timer()

        fired.assert_not_awaited()
        assert scheduler.pending_count == 0
    finally:
        parked.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("pause", list(PAUSES))
async def test_a_retired_pause_leaves_the_registry_and_refuses_a_late_answer(pause: str) -> None:
    """The late answer or Skip on the stale card reaches the manual path, which must be told it is already resolved (409)."""
    parked = _parked_at(CHAT_ID, pause)
    try:
        release_parked_hitl(CHAT_ID)

        assert ACTIVE_COLLECTORS.get(CHAT_ID) is None
        assert ApprovalTimeoutScheduler.get().resolve_if_first(CHAT_ID) is False
    finally:
        parked.cleanup()


@pytest.mark.asyncio
async def test_a_chat_that_waits_for_no_answer_is_left_alone() -> None:
    """A plain run holds no card: nothing to retire, and the arbiter must stay open for the next real pause."""
    running = StreamContentCollector(chat_id=CHAT_ID)
    running.feed_event({"type": "message", "messageId": "msg-1", "data": "working"})
    try:
        release_parked_hitl(CHAT_ID)

        assert ACTIVE_COLLECTORS.get(CHAT_ID) is running
        assert ApprovalTimeoutScheduler.get().resolve_if_first(CHAT_ID) is True
    finally:
        running.cleanup()


@pytest.mark.asyncio
async def test_a_chat_without_a_registered_run_is_left_alone() -> None:
    release_parked_hitl(CHAT_ID)

    assert ApprovalTimeoutScheduler.get().resolve_if_first(CHAT_ID) is True


@pytest.mark.asyncio
async def test_the_pause_of_another_chat_is_left_alone() -> None:
    fired = AsyncMock()
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.schedule("chat-other", FAST, "deny", fired)
    other = _parked_at("chat-other", "clarification")
    try:
        release_parked_hitl(CHAT_ID)
        await _wait_past_the_timer()

        fired.assert_awaited_once()
        assert ACTIVE_COLLECTORS.get("chat-other") is other
    finally:
        other.cleanup()


@pytest.mark.asyncio
async def test_a_new_pause_after_the_release_is_armed_and_answerable() -> None:
    """The release must not poison the chat: the run that follows stops at a card of its own, its timer fires, a manual answer is taken."""
    old = _parked_at(CHAT_ID, "clarification")
    release_parked_hitl(CHAT_ID)
    old.cleanup()

    fired = AsyncMock()
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.schedule(CHAT_ID, FAST, "deny", fired)
    await _wait_past_the_timer()
    fired.assert_awaited_once()

    scheduler.schedule(CHAT_ID, 60, "deny", fired)
    assert scheduler.resolve_if_first(CHAT_ID) is True


@pytest.mark.asyncio
async def test_releasing_twice_is_the_same_as_once() -> None:
    parked = _parked_at(CHAT_ID, "clarification")
    try:
        release_parked_hitl(CHAT_ID)
        release_parked_hitl(CHAT_ID)

        assert ACTIVE_COLLECTORS.get(CHAT_ID) is None
        assert ApprovalTimeoutScheduler.get().resolve_if_first(CHAT_ID) is False
    finally:
        parked.cleanup()
