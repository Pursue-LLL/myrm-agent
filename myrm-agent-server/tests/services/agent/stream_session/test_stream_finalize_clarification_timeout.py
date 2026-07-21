"""Tests finalize schedules clarification timeout when ask_question interrupts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.stream_session.stream_finalize import finalize_agent_stream_session
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, ClarificationTimeoutHolder


def _make_session(chat_id: str = "chat-clarify-1") -> MagicMock:
    session = MagicMock()
    session.request.chat_id = chat_id
    session.request.timezone = "UTC"
    session.collector.has_persistable_turn = False
    session.collector.has_content = False
    session.collector.cleanup = MagicMock()
    session.monitor.stop = AsyncMock()
    session.cancel_token.is_cancelled = False
    session.params = MagicMock()
    session.params.message_id = "msg-1"
    return session


@pytest.mark.asyncio
async def test_finalize_schedules_clarification_timeout_when_pending() -> None:
    session = _make_session()
    clarification = ClarificationTimeoutHolder(pending=True)

    with (
        patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
        patch(
            "app.services.agent.stream_session.stream_finalize.schedule_clarification_timeout"
        ) as mock_schedule,
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(
            session,
            MagicMock(),
            ApprovalTimeoutHolder(),
            clarification,
        )

    mock_schedule.assert_called_once_with(chat_id="chat-clarify-1", params=session.params)


@pytest.mark.asyncio
async def test_finalize_skips_clarification_timeout_when_not_pending() -> None:
    session = _make_session()

    with (
        patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
        patch(
            "app.services.agent.stream_session.stream_finalize.schedule_clarification_timeout"
        ) as mock_schedule,
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(
            session,
            MagicMock(),
            ApprovalTimeoutHolder(),
            ClarificationTimeoutHolder(pending=False),
        )

    mock_schedule.assert_not_called()
