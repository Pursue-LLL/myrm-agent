"""Tests for durable offline task resume notifications in system.py.

Validates that:
1. Failed durable resume creates type="error" SystemNotification
2. Successful durable resume creates type="success" SystemNotification
3. Notification failure during resume does not crash the worker
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_task_record(
    *,
    task_id: str = "task-001",
    chat_id: str = "chat-resume-123",
    action_mode: str = "general",
) -> MagicMock:
    record = MagicMock()
    record.id = task_id
    record.chat_id = chat_id
    record.action_mode = action_mode
    record.serialized_params = {
        "chat_id": chat_id,
        "query": "test query",
        "message_id": "msg-test",
        "model_cfg": {"provider": "test", "model": "test-model"},
    }
    return record


@pytest.mark.asyncio
async def test_resume_failure_creates_error_notification():
    """When durable resume raises an exception, an error notification is created."""
    task_record = _make_task_record()

    mock_notif = AsyncMock()
    mock_session_factory = MagicMock()
    mock_db = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.platform_utils.get_session_factory", return_value=mock_session_factory),
        patch("app.platform_utils.get_checkpointer", return_value=MagicMock()),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch("app.services.agent.streaming.ai_agent_service_stream") as mock_stream,
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(), chat_id="chat-resume-123", query="test", message_id="msg-test"
        )
        mock_stream.side_effect = RuntimeError("LLM provider unavailable")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [task_record]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        from app.lifecycle.system import resume_durable_offline_tasks

        await resume_durable_offline_tasks()

        await asyncio.sleep(0.1)

    error_calls = [c for c in mock_notif.call_args_list if c[1].get("type") == "error"]
    assert len(error_calls) >= 1
    call_kwargs = error_calls[0][1]
    assert call_kwargs["title"] == "Task Resume Failed"
    assert call_kwargs["source"] == "offline_guardian"
    assert call_kwargs["meta_data"]["chat_id"] == "chat-resume-123"
    assert call_kwargs["meta_data"]["action_url"] == "/chat-resume-123"


@pytest.mark.asyncio
async def test_resume_success_creates_success_notification():
    """When durable resume succeeds, a success notification is created."""
    task_record = _make_task_record()

    mock_notif = AsyncMock()
    mock_session_factory = MagicMock()
    mock_db = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    async def _fake_stream(*args, **kwargs):
        yield "data: done\n\n"

    with (
        patch("app.platform_utils.get_session_factory", return_value=mock_session_factory),
        patch("app.platform_utils.get_checkpointer", return_value=MagicMock()),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch("app.services.agent.streaming.ai_agent_service_stream", side_effect=_fake_stream),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(), chat_id="chat-resume-123", query="test", message_id="msg-test"
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [task_record]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        from app.lifecycle.system import resume_durable_offline_tasks

        await resume_durable_offline_tasks()

        await asyncio.sleep(0.1)

    success_calls = [c for c in mock_notif.call_args_list if c[1].get("type") == "success"]
    assert len(success_calls) >= 1
    call_kwargs = success_calls[0][1]
    assert "Completed" in call_kwargs["title"] or "completed" in call_kwargs["title"].lower()


@pytest.mark.asyncio
async def test_notification_failure_does_not_crash_resume():
    """If notification creation fails, the resume worker should not crash."""
    task_record = _make_task_record()

    mock_session_factory = MagicMock()
    mock_db = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.platform_utils.get_session_factory", return_value=mock_session_factory),
        patch("app.platform_utils.get_checkpointer", return_value=MagicMock()),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(side_effect=Exception("DB connection lost")),
        ),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch("app.services.agent.streaming.ai_agent_service_stream") as mock_stream,
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(), chat_id="chat-resume-123", query="test", message_id="msg-test"
        )
        mock_stream.side_effect = RuntimeError("LLM error")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [task_record]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        from app.lifecycle.system import resume_durable_offline_tasks

        await resume_durable_offline_tasks()

        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_no_checkpointer_skips_resume():
    """If no checkpointer is available, resume is skipped entirely."""
    mock_notif = AsyncMock()

    with (
        patch("app.platform_utils.get_checkpointer", return_value=None),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
    ):
        from app.lifecycle.system import resume_durable_offline_tasks

        await resume_durable_offline_tasks()

    mock_notif.assert_not_called()
