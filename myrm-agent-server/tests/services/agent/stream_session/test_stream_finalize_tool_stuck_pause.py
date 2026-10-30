"""Finalize closes a run that a tool_stuck pause ended, and keeps open a run that waits on a card."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

from app.services.agent.params.models import TurnCapabilityTelemetryRequest
from app.services.agent.stream_session.stream_finalize import finalize_agent_stream_session
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, ClarificationTimeoutHolder
from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector

CHAT_ID = "chat-tool-stuck-finalize"
PAUSED_STEP = {"step_key": "tool_stuck_paused", "items": [], "status": "error"}
TOOL_STUCK_EVENT: dict[str, object] = {
    "type": "approval_required",
    "data": {"action_type": "tool_stuck", "tool_name": "bash_code_execute_tool", "tool_call_id": "call-1"},
}
PENDING_CARD_EVENT: dict[str, object] = {
    "type": "approval_required",
    "data": {"action_type": "browser_takeover", "url": "https://example.com"},
}


class _Outcome:
    """What one finalize call did to the run digest, the turn telemetry and the stored message."""

    def __init__(self) -> None:
        self.end_run = MagicMock()
        self.send_completed = AsyncMock(return_value=True)
        self.send_failed = AsyncMock(return_value=True)
        self.persist = AsyncMock()


def _make_session() -> MagicMock:
    session = MagicMock()
    session.request.chat_id = CHAT_ID
    session.request.message_id = "msg-1"
    session.request.timezone = "UTC"
    session.request.resume_value = None
    session.request.turn_capability_telemetry = TurnCapabilityTelemetryRequest(
        source="direct", effective_skill_count=0, effective_mcp_count=0
    )
    session.collector = StreamContentCollector(chat_id=CHAT_ID)
    session.cancel_token.is_cancelled = False
    session.params = MagicMock()
    session.params.message_id = "msg-1"
    session.extra_context = {}
    session.stream_ttft_ms = None
    session.had_fatal_error = False
    session.migration_live_readiness_status = None
    session.turn_capability_terminal_recorded = False
    return session


@pytest_asyncio.fixture(autouse=True)
async def _release_collector() -> AsyncIterator[None]:
    yield
    ACTIVE_COLLECTORS.pop(CHAT_ID, None)


async def _finalize(session: MagicMock) -> _Outcome:
    outcome = _Outcome()
    with (
        patch("app.services.agent.stream_session.stream_finalize.user_credentials_ctx") as mock_ctx,
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
        patch("app.services.agent.stream_session.stream_finalize.merge_memory_citation_fallback"),
        patch(
            "app.services.agent.stream_session.stream_finalize.record_migration_first_turn_outcome",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.agent.stream_session.turn_capability_terminal.record_turn_capability_send_completed",
            outcome.send_completed,
        ),
        patch(
            "app.services.agent.stream_session.turn_capability_terminal.record_turn_capability_send_failed", outcome.send_failed
        ),
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", outcome.persist),
        patch("app.services.copilot.run_digest_store.RunDigestStore.end_run", outcome.end_run),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(
            session, MagicMock(), ApprovalTimeoutHolder(), ClarificationTimeoutHolder(pending=False)
        )
    return outcome


@pytest.mark.asyncio
async def test_a_tool_stuck_pause_ends_the_run_like_a_finished_turn() -> None:
    session = _make_session()
    session.collector.feed_event(TOOL_STUCK_EVENT)

    outcome = await _finalize(session)

    outcome.end_run.assert_called_once_with(CHAT_ID, phase=RunDigestPhase.COMPLETED, progress_steps=[PAUSED_STEP])
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is None


@pytest.mark.asyncio
async def test_a_tool_stuck_pause_is_a_completed_send_not_a_failed_one() -> None:
    session = _make_session()
    session.collector.feed_event(TOOL_STUCK_EVENT)

    outcome = await _finalize(session)

    outcome.send_completed.assert_awaited_once()
    outcome.send_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_tool_stuck_pause_is_stored_with_the_step_that_says_why() -> None:
    session = _make_session()
    session.collector.feed_event(TOOL_STUCK_EVENT)

    outcome = await _finalize(session)

    outcome.persist.assert_awaited_once()
    persisted = outcome.persist.await_args
    assert persisted is not None
    assert persisted.kwargs["extra_data"]["progressSteps"] == [PAUSED_STEP]


@pytest.mark.asyncio
async def test_a_run_waiting_on_a_card_stays_open() -> None:
    session = _make_session()
    session.collector.feed_event(PENDING_CARD_EVENT)

    outcome = await _finalize(session)

    outcome.end_run.assert_not_called()
    outcome.send_completed.assert_not_awaited()
    outcome.send_failed.assert_not_awaited()
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is session.collector


@pytest.mark.asyncio
async def test_an_empty_run_that_was_not_paused_is_still_a_failed_send() -> None:
    session = _make_session()

    outcome = await _finalize(session)

    outcome.send_failed.assert_awaited_once_with(session.request, "unknown_error")
    outcome.send_completed.assert_not_awaited()
