"""A tool_stuck pause ends the turn: it is no unanswered card, and the transcript keeps a step that says why."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector
from tests.support.harness_pause_event import harness_pause_event

CHAT_ID = "chat-tool-stuck-collector"
PAUSED_STEP = {"step_key": "tool_stuck_paused", "items": [], "status": "error"}


@pytest.fixture(autouse=True)
def _release_collector() -> Iterator[None]:
    yield
    ACTIVE_COLLECTORS.pop(CHAT_ID, None)


def _steps(collector: StreamContentCollector) -> list[dict[str, object]]:
    extra_data = collector.extra_data or {}
    steps = extra_data.get("progressSteps")
    return list(steps) if isinstance(steps, list) else []


def test_a_pause_is_not_an_unanswered_card() -> None:
    collector = StreamContentCollector(chat_id=CHAT_ID)

    collector.feed_event(harness_pause_event())

    assert collector.tool_stuck_paused is True
    assert collector.has_pending_hitl_replay() is False


def test_a_pause_is_saved_as_a_step_the_transcript_can_show() -> None:
    collector = StreamContentCollector(chat_id=CHAT_ID)

    collector.feed_event(harness_pause_event())

    assert _steps(collector) == [PAUSED_STEP]
    assert collector.has_persistable_turn is True


def test_a_pause_that_arrives_twice_is_saved_once() -> None:
    collector = StreamContentCollector(chat_id=CHAT_ID)

    collector.feed_event(harness_pause_event())
    collector.feed_event(harness_pause_event())

    assert _steps(collector) == [PAUSED_STEP]


def test_a_client_attached_to_the_stream_still_receives_the_pause() -> None:
    collector = StreamContentCollector(chat_id=CHAT_ID)
    _, queue = collector.subscribe()
    event = harness_pause_event()

    collector.feed_event(event)

    assert queue.get_nowait() == event


@pytest.mark.parametrize(
    "event",
    [
        {"type": "approval_required", "data": {"action_type": "browser_takeover", "url": "https://example.com"}},
        {"type": "approval_required", "data": {"message": "Approve the plan?"}},
        {"type": "approval_required", "data": "not a mapping"},
        {"type": "tool_approval_request", "data": {"actionRequests": [{"action": "bash"}]}},
    ],
)
def test_every_other_interrupt_stays_an_unanswered_card(event: dict[str, object]) -> None:
    collector = StreamContentCollector(chat_id=CHAT_ID)

    collector.feed_event(event)

    assert collector.has_pending_hitl_replay() is True
    assert collector.tool_stuck_paused is False
    assert PAUSED_STEP not in _steps(collector)
