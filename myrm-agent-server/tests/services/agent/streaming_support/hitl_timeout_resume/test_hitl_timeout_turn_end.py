"""A turn that a fired timer resumed ends with the steps a request's finalize ends a turn with.

The lifecycle event feeds outbound webhooks and push notifications, the history record keeps the next turn on the warm agent
thread, the compaction steps drain what the run left behind, and the stored form of the answer is the one a request's turn gets.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.streaming_support import hitl_timeout
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.event.app_event_bus import AppEventType
from tests.support.hitl_timeout_run import CHAT_ID, granted_lease, params_of_the_card, stopped_lease

_RESUME_MODE_EVENT: dict[str, object] = {"type": "message_end", "token_economics": {"turn_context": {"history_mode": "resume"}}}


async def _resume(lease: Callable[[str, str], AbstractAsyncContextManager[MagicMock]] = granted_lease) -> None:
    with patch.object(hitl_timeout, "server_turn_lease", lease):
        await hitl_timeout._resume_after_timeout(CHAT_ID, params_of_the_card(), {"decision": "deny"}, "approval")


def _stream_of(*events: dict[str, object]) -> AbstractContextManager[object]:
    async def stream(**_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        for event in events:
            yield event

    return patch("app.services.agent.streaming.ai_agent_service_stream", new=stream)


def _published_events() -> tuple[MagicMock, AbstractContextManager[object]]:
    bus = MagicMock()
    return bus, patch("app.services.event.app_event_bus.get_event_bus", return_value=bus)


@pytest.mark.asyncio
async def test_the_lifecycle_webhook_announces_the_turn_the_timer_run_completed(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    bus, bus_patch = _published_events()
    with bus_patch:
        await _resume()

    bus.publish.assert_called_once()
    event = bus.publish.call_args.args[0]
    assert event.event_type == AppEventType.SESSION_COMPLETED
    assert event.data == {
        "chat_id": CHAT_ID,
        "agent_id": "agent-timer",
        "phase": "completed",
        "was_cancelled": False,
        "had_fatal_error": False,
    }


@pytest.mark.asyncio
async def test_the_lifecycle_webhook_announces_a_timer_run_the_user_stopped_as_failed(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    bus, bus_patch = _published_events()
    with bus_patch:
        await _resume(stopped_lease)

    event = bus.publish.call_args.args[0]
    assert event.event_type == AppEventType.SESSION_FAILED
    assert event.data["phase"] == "cancelled"
    assert event.data["was_cancelled"] is True


@pytest.mark.asyncio
async def test_a_timer_run_the_user_stopped_is_stored_as_stopped_with_its_reason(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    """Without the mark the stopped turn is stored like an unfinished one: no stop notice, and a page attached to the run is never told."""
    persist = AsyncMock()
    with patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new=persist):
        await _resume(stopped_lease)

    stored = persist.await_args
    assert stored is not None
    extra_data = stored.kwargs["extra_data"]
    assert extra_data["completionStatus"] == "cancelled"
    assert extra_data["stopReason"]["category"] == "cancelled"
    assert extra_data["stopReason"]["message"] == "Cancelled by user"


@pytest.mark.asyncio
async def test_a_timer_run_that_finished_is_not_stored_as_stopped(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    persist = AsyncMock()
    with patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new=persist):
        await _resume()

    stored = persist.await_args
    assert stored is not None
    assert "completionStatus" not in stored.kwargs["extra_data"]
    assert "stopReason" not in stored.kwargs["extra_data"]


@pytest.mark.asyncio
async def test_no_lifecycle_event_while_the_turn_waits_at_another_card(
    parked: StreamContentCollector, resumed_run: list[bool], stops_at_a_card: list[bool]
) -> None:
    stops_at_a_card.append(True)
    bus, bus_patch = _published_events()
    with bus_patch:
        await _resume()

    bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_the_thread_is_recorded_as_in_sync_when_the_timer_run_completed_on_it(
    parked: StreamContentCollector, resumed_run: list[bool]
) -> None:
    """Without the record the next turn rebuilds the thread: the tool traces and the warm provider prefix are lost."""
    commit = AsyncMock()
    with (
        _stream_of({"type": "message", "data": "continued"}, _RESUME_MODE_EVENT),
        patch("app.services.agent.stream_session.turn_history_sync.commit_history_sync", new=commit),
    ):
        await _resume()

    commit.assert_awaited_once_with(CHAT_ID, "msg-1")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["stops_at_a_card", "stopped_by_the_user", "ran_off_the_thread"])
async def test_the_thread_is_not_recorded_as_in_sync_when_the_turn_did_not_complete_on_it(
    parked: StreamContentCollector, resumed_run: list[bool], stops_at_a_card: list[bool], case: str
) -> None:
    commit = AsyncMock()
    events: list[dict[str, object]] = [{"type": "message", "data": "continued"}]
    if case != "ran_off_the_thread":
        events.append(_RESUME_MODE_EVENT)
    if case == "stops_at_a_card":
        events.append({"type": "tool_approval_request", "messageId": "msg-1", "data": {"actionRequests": []}})
    with (
        _stream_of(*events),
        patch("app.services.agent.stream_session.turn_history_sync.commit_history_sync", new=commit),
    ):
        await _resume(stopped_lease if case == "stopped_by_the_user" else granted_lease)

    commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stops_at_card", [False, True])
async def test_the_compaction_state_of_the_timer_run_is_released_and_its_debt_drained(
    parked: StreamContentCollector, resumed_run: list[bool], stops_at_a_card: list[bool], stops_at_card: bool
) -> None:
    """Released whether the turn ends or waits at a card, as a request's finalize releases it."""
    if stops_at_card:
        stops_at_a_card.append(True)
    drain = MagicMock()
    flush_telemetry = MagicMock()
    clear_metrics = MagicMock()
    with (
        patch("myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics") as metrics,
        patch("app.services.chat.chat_service.ChatService.schedule_background_drain", new=drain),
        patch.object(hitl_timeout, "enqueue_context_compaction_telemetry", new=flush_telemetry),
        patch.object(hitl_timeout, "clear_context_task_metrics", new=clear_metrics),
    ):
        metrics.return_value = MagicMock(compaction_debt_pending=True)
        await _resume()

    drain.assert_called_once_with(CHAT_ID)
    flush_telemetry.assert_called_once_with(CHAT_ID)
    clear_metrics.assert_called_once_with(CHAT_ID)


@pytest.mark.asyncio
async def test_a_timer_run_that_only_asks_a_question_is_stored(parked: StreamContentCollector, resumed_run: list[bool]) -> None:
    """The card has no answer text yet it is part of the turn: a reload must still show it."""
    persist = AsyncMock()
    with (
        _stream_of({"type": "clarification_required", "messageId": "msg-1", "data": {"title": "Which one?"}}),
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new=persist),
    ):
        await _resume()

    persist.assert_awaited_once()
    stored = persist.await_args
    assert stored is not None
    assert stored.kwargs["extra_data"]["clarification"]["answered"] is False


@pytest.mark.asyncio
async def test_the_stored_answer_is_the_one_a_requests_turn_gets(parked: StreamContentCollector, resumed_run: list[bool]) -> None:
    """Citation tags are lifted out of the text into the citations list, and the row carries the user's timezone."""
    persist = AsyncMock()
    with (
        _stream_of({"type": "message", "data": "done <cite:mem-1> ok"}),
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new=persist),
    ):
        await _resume()

    stored = persist.await_args
    assert stored is not None
    assert stored.args == (CHAT_ID, "done  ok")
    assert stored.kwargs["extra_data"]["citations"] == ["mem-1"]
    assert stored.kwargs["timezone"] == "Asia/Shanghai"
    assert stored.kwargs["request_message_id"] == "msg-1"
