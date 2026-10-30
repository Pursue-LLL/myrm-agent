"""What the run a fired approval timer starts is given: the stored history, and the timer of the next card it stops at.

The resume of a page reads the stored history, which holds the user message that opened the turn, and it finds the turn's skill
hooks in that message. The params the timer captured when the card appeared hold the history from before it. A run that stops at
a card of its own has no collector holding that card, so the timer armed for it is what answers it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.streaming_support import hitl_timeout
from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector
from tests.support.hitl_timeout_run import CHAT_ID, granted_lease, params_of_the_card


@pytest.mark.asyncio
async def test_the_timer_run_reads_the_history_a_page_driven_resume_reads(
    parked: StreamContentCollector,
    resumed_run: list[bool],
    stored_history: AsyncMock,
    received_params: list[object],
) -> None:
    """A resume finds the turn's skill hooks in the user message that opened the turn.

    The params the timer captured hold the history from before that message, so the run would start without the hooks.
    """
    turn_history = [["human", "[use probe] run the command"], ["assistant", "on it"]]
    stored_history.return_value = turn_history

    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "allow"}, "approval")

    stored_history.assert_awaited_once_with(CHAT_ID)
    assert [getattr(p, "chat_history", None) for p in received_params] == [turn_history]


@pytest.mark.asyncio
async def test_a_timer_run_that_stops_at_another_card_arms_the_timer_of_that_card(
    parked: StreamContentCollector,
    resumed_run: list[bool],
    stops_at_a_card: list[bool],
    armed_timer: MagicMock,
    received_params: list[object],
) -> None:
    """Nobody holds the next card, so its own timer is what answers it: with the card's seconds and behavior, on the run's params."""
    stops_at_a_card.append(True)
    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "allow"}, "approval")

    armed_timer.assert_called_once()
    assert armed_timer.call_args.args[0] == CHAT_ID
    assert armed_timer.call_args.args[1] is received_params[0]
    assert armed_timer.call_args.kwargs == {
        "approval_timeout": {"seconds": 45, "behavior": "allow"},
        "clarification_pending": False,
        "awaiting_answer": True,
    }


@pytest.mark.asyncio
async def test_a_timer_run_that_ends_the_turn_arms_no_timer(
    parked: StreamContentCollector, resumed_run: list[bool], armed_timer: MagicMock
) -> None:
    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    armed_timer.assert_called_once()
    assert armed_timer.call_args.kwargs == {
        "approval_timeout": None,
        "clarification_pending": False,
        "awaiting_answer": False,
    }


@pytest.mark.asyncio
async def test_a_timer_run_that_cannot_read_the_history_hands_the_card_back(
    parked: StreamContentCollector, resumed_run: list[bool], stored_history: AsyncMock, received_params: list[object]
) -> None:
    """Failing before the agent starts is a failed run like any other: the card goes back and no run starts."""
    stored_history.side_effect = RuntimeError("database is locked")
    scheduler = ApprovalTimeoutScheduler.get()
    with (
        patch.object(hitl_timeout, "server_turn_lease", granted_lease),
        patch.object(scheduler, "reopen") as reopen,
        pytest.raises(RuntimeError, match="database is locked"),
    ):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    reopen.assert_called_once_with(CHAT_ID)
    assert received_params == []
    assert parked.has_pending_tool_approval() is True
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is parked
