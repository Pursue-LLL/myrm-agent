"""The run a fired timer starts is the chat's collector while it works, so what a page asks for reaches it.

A page that reloads while the timer run works attaches to that run, and the card the run stops at is held by it: the turn
state reports it and a reload gets it back. A chain of cards each answered by its own timer hands the chat from run to run.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

from app.services.agent.streaming_support import hitl_timeout
from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector
from tests.support.hitl_timeout_run import CHAT_ID, digest_phase, granted_lease, params_of_the_card


@pytest.mark.asyncio
async def test_a_page_that_attaches_while_the_timer_run_works_gets_that_run(
    parked: StreamContentCollector, resumed_run: list[bool], registered_runs: list[StreamContentCollector | None]
) -> None:
    """The snapshot an attaching page is given holds what the run has produced so far, not the parked run's old turn."""
    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    attached_run = registered_runs[0]
    assert attached_run is not None
    assert attached_run.get_snapshot()["content"] == "continued"


@pytest.mark.asyncio
async def test_the_card_a_timer_run_stops_at_is_held_by_that_run(
    parked: StreamContentCollector,
    resumed_run: list[bool],
    stops_at_a_card: list[bool],
    registered_runs: list[StreamContentCollector | None],
) -> None:
    """A tool-approval card has no stored record: a reload gets it back only from the collector that holds it."""
    stops_at_a_card.append(True)
    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    holder = ACTIVE_COLLECTORS.get(CHAT_ID)
    assert holder is registered_runs[0]
    assert holder is not None
    assert holder.has_pending_tool_approval() is True
    _snapshot, queue = holder.subscribe()
    assert queue.get_nowait()["type"] == "tool_approval_request"


@pytest.mark.asyncio
async def test_the_timer_of_the_next_card_answers_it_and_ends_the_turn(
    parked: StreamContentCollector, resumed_run: list[bool], stops_at_a_card: list[bool]
) -> None:
    """Chained cards: the second timer finds the card in the first run's collector, and the turn ends with the second run."""
    stops_at_a_card.append(True)
    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")
        stops_at_a_card.clear()
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert resumed_run == [False, False]
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is None
    assert digest_phase() is RunDigestPhase.COMPLETED


@pytest.mark.asyncio
async def test_a_failed_second_timer_run_hands_the_next_card_back_to_the_run_that_held_it(
    parked: StreamContentCollector, resumed_run: list[bool], stops_at_a_card: list[bool]
) -> None:
    stops_at_a_card.append(True)
    scheduler = ApprovalTimeoutScheduler.get()

    async def failing_stream(**_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        raise RuntimeError("boom")
        yield {}  # pragma: no cover - makes this a generator

    with patch.object(hitl_timeout, "server_turn_lease", granted_lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")
        first_run = ACTIVE_COLLECTORS.get(CHAT_ID)
        with (
            patch("app.services.agent.streaming.ai_agent_service_stream", new=failing_stream),
            patch.object(scheduler, "reopen") as reopen,
            pytest.raises(RuntimeError, match="boom"),
        ):
            await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert first_run is not None
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is first_run
    assert first_run.has_pending_tool_approval() is True
    reopen.assert_called_once_with(CHAT_ID)


@pytest.mark.asyncio
async def test_a_page_attached_to_the_parked_run_ends_when_the_timer_run_takes_the_chat(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    """The attach stream of a page ends when the registry no longer names the run it attached to; the page then reconciles."""
    attached_to = ACTIVE_COLLECTORS.get(CHAT_ID)
    assert attached_to is parked
    still_named_during_run: list[bool] = []

    async def stream(**_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        still_named_during_run.append(ACTIVE_COLLECTORS.get(CHAT_ID) is parked)
        await asyncio.sleep(0)
        yield {"type": "message", "data": "continued"}

    with (
        patch("app.services.agent.streaming.ai_agent_service_stream", new=stream),
        patch.object(hitl_timeout, "server_turn_lease", granted_lease),
    ):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")

    assert still_named_during_run == [False]
