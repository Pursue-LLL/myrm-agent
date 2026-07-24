"""Tests for clarification answered persistence in stream_finalize."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.dto import MessageDTO
from app.services.agent.stream_session.stream_finalize import (
    _mark_pending_clarification_answered,
    finalize_agent_stream_session,
)
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, ClarificationTimeoutHolder


def _message(
    *,
    msg_id: str,
    role: str,
    extra_data: dict[str, object] | None = None,
    created_at: datetime | None = None,
) -> MessageDTO:
    ts = created_at or datetime(2025, 6, 1, 10, 0, 0)
    return MessageDTO(
        id=msg_id,
        chat_id="chat-clarify",
        role=role,
        content="content",
        sent_at=ts,
        sent_timezone="UTC",
        created_at=ts,
        extra_data=extra_data,
    )


@pytest.mark.asyncio
async def test_mark_pending_clarification_answered_patches_latest_assistant() -> None:
    messages = [
        _message(
            msg_id="user-1",
            role="user",
            extra_data={"original_query": "Plan a trip"},
        ),
        _message(
            msg_id="assistant-clarify",
            role="assistant",
            extra_data={
                "clarification": {
                    "answered": False,
                    "title": "Destination",
                    "isResumeMode": True,
                }
            },
        ),
        _message(
            msg_id="assistant-followup",
            role="assistant",
            extra_data={},
        ),
    ]

    with patch(
        "app.services.chat.chat_service.ChatService.get_all_messages",
        new_callable=AsyncMock,
        return_value=messages,
    ), patch(
        "app.services.chat.chat_service.ChatService.update_message_extra_data",
        new_callable=AsyncMock,
    ) as mock_update:
        await _mark_pending_clarification_answered("chat-clarify")

    mock_update.assert_awaited_once()
    assert mock_update.await_args.args[0] == "assistant-clarify"
    updated_extra = mock_update.await_args.args[1]
    clarification = updated_extra.get("clarification")
    assert isinstance(clarification, dict)
    assert clarification.get("answered") is True
    assert clarification.get("title") == "Destination"


@pytest.mark.asyncio
async def test_mark_pending_clarification_answered_noop_when_already_answered() -> None:
    messages = [
        _message(
            msg_id="assistant-clarify",
            role="assistant",
            extra_data={"clarification": {"answered": True}},
        ),
    ]

    with patch(
        "app.services.chat.chat_service.ChatService.get_all_messages",
        new_callable=AsyncMock,
        return_value=messages,
    ), patch(
        "app.services.chat.chat_service.ChatService.update_message_extra_data",
        new_callable=AsyncMock,
    ) as mock_update:
        await _mark_pending_clarification_answered("chat-clarify")

    mock_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_marks_clarification_answered_after_successful_resume() -> None:
    session = MagicMock()
    session.request = MagicMock()
    session.request.chat_id = "chat-clarify"
    session.request.resume_value = {"framework": "langchain"}
    session.request.timezone = "UTC"
    session.request.use_workflow = False
    session.cancel_token = MagicMock()
    session.cancel_token.is_cancelled = False
    session.params = MagicMock()
    session.params.message_id = "user-request-id"
    session.params.model_cfg = MagicMock()
    session.params.locale = "en"
    session.collector = MagicMock()
    session.collector.has_persistable_turn = False
    session.collector.has_content = False
    session.collector.cleanup = MagicMock()
    session.collector.cross_turn_data_updates = {}
    session.collector.has_pending_hitl_replay = MagicMock(return_value=False)
    session.monitor = MagicMock()
    session.monitor.stop = AsyncMock()
    session.extra_context = {}
    session.stream_ttft_ms = None
    session.had_fatal_error = False

    clarification = ClarificationTimeoutHolder()
    clarification.pending = False

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "app.services.agent.stream_session.stream_finalize._mark_pending_clarification_answered",
            new_callable=AsyncMock,
        ) as mock_mark,
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(
            session,
            MagicMock(),
            ApprovalTimeoutHolder(),
            clarification,
        )

    mock_mark.assert_awaited_once_with("chat-clarify")


@pytest.mark.asyncio
async def test_finalize_marks_clarification_answered_after_dr_resolved_status() -> None:
    session = MagicMock()
    session.request = MagicMock()
    session.request.chat_id = "chat-clarify"
    session.request.resume_value = None
    session.request.timezone = "UTC"
    session.request.use_workflow = False
    session.cancel_token = MagicMock()
    session.cancel_token.is_cancelled = False
    session.params = MagicMock()
    session.params.message_id = "dr-stream-id"
    session.params.model_cfg = MagicMock()
    session.params.locale = "en"
    session.collector = MagicMock()
    session.collector.has_persistable_turn = False
    session.collector.has_content = False
    session.collector.extra_data = {"clarification": {"answered": True, "isResumeMode": False}}
    session.collector.cleanup = MagicMock()
    session.collector.cross_turn_data_updates = {}
    session.collector.has_pending_hitl_replay = MagicMock(return_value=False)
    session.monitor = MagicMock()
    session.monitor.stop = AsyncMock()
    session.extra_context = {}
    session.stream_ttft_ms = None
    session.had_fatal_error = False

    clarification = ClarificationTimeoutHolder()
    clarification.pending = False

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "app.services.agent.stream_session.stream_finalize._mark_pending_clarification_answered",
            new_callable=AsyncMock,
        ) as mock_mark,
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(
            session,
            MagicMock(),
            ApprovalTimeoutHolder(),
            clarification,
        )

    mock_mark.assert_awaited_once_with("chat-clarify")
