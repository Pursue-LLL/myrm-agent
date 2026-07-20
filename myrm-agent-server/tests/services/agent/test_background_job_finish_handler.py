"""Tests for ServerBackgroundJobFinishHandler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.api.hooks import BackgroundJobFinishResult

from app.services.agent.background_job_finish_handler import (
    ServerBackgroundJobFinishHandler,
    _command_preview,
    _format_finish_message,
    _resolve_user_locale,
)

_TEST_JOB_ID = "b" * 32


def test_format_finish_message_success_en() -> None:
    msg = _format_finish_message(
        BackgroundJobFinishResult(
            session_id="chat-1",
            pid=42,
            command="npm run dev",
            status="exited",
            exit_code=0,
            error_category=None,
        ),
        "en",
    )
    assert "completed" in msg
    assert "42" in msg


def test_format_finish_message_success_zh() -> None:
    msg = _format_finish_message(
        BackgroundJobFinishResult(
            session_id="chat-1",
            pid=42,
            command="npm run dev",
            status="exited",
            exit_code=0,
            error_category=None,
        ),
        "zh-CN",
    )
    assert "已完成" in msg
    assert "42" in msg


@pytest.mark.asyncio
async def test_handler_appends_message_and_publishes_event() -> None:
    handler = ServerBackgroundJobFinishHandler()
    result = BackgroundJobFinishResult(
        session_id="chat-abc",
        pid=7,
        command="sleep 1",
        status="exited",
        exit_code=0,
        error_category=None,
    )

    mock_bus = MagicMock()
    with (
        patch(
            "app.services.agent.background_job_finish_handler._resolve_user_locale",
            AsyncMock(return_value="en"),
        ),
        patch(
            "app.services.agent.background_job_finish_handler.ChatService.append_message",
            AsyncMock(),
        ) as mock_append,
        patch(
            "app.services.agent.background_job_finish_handler.get_event_bus",
            return_value=mock_bus,
        ),
    ):
        await handler._process(result)

    mock_append.assert_awaited_once()
    assert mock_append.await_args.kwargs["chat_id"] == "chat-abc"
    assert mock_append.await_args.kwargs["role"] == "assistant"
    mock_bus.publish.assert_called_once()
    published = mock_bus.publish.call_args[0][0]
    assert published.data["meta_data"]["kind"] == "background_job_finish"
    assert published.data["title"] == "Background task finished"


@pytest.mark.asyncio
async def test_on_background_job_finish_delegates_to_process() -> None:
    handler = ServerBackgroundJobFinishHandler()
    result = BackgroundJobFinishResult(
        session_id="chat-delegate",
        pid=3,
        command="x",
        status="exited",
        exit_code=0,
        error_category=None,
        job_id=_TEST_JOB_ID,
    )

    with patch.object(handler, "_process", AsyncMock()) as mock_process:
        await handler.on_background_job_finish(result)

    mock_process.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_handler_skips_non_exited_status() -> None:
    handler = ServerBackgroundJobFinishHandler()
    result = BackgroundJobFinishResult(
        session_id="chat-abc",
        pid=7,
        command="sleep 1",
        status="killed",
        exit_code=None,
        error_category=None,
    )

    with patch(
        "app.services.agent.background_job_finish_handler.ChatService.append_message",
        AsyncMock(),
    ) as mock_append:
        await handler.on_background_job_finish(result)

    mock_append.assert_not_called()


def test_command_preview_truncates_long_commands() -> None:
    long_cmd = "x" * 200
    preview = _command_preview(long_cmd)
    assert len(preview) == 120
    assert preview.endswith("...")


def test_format_finish_message_with_error_category() -> None:
    msg = _format_finish_message(
        BackgroundJobFinishResult(
            session_id="chat-1",
            pid=9,
            command="bad",
            status="exited",
            exit_code=137,
            error_category="oom_killed",
        ),
        "en",
    )
    assert "oom_killed" in msg


def test_format_finish_message_generic_branch() -> None:
    msg = _format_finish_message(
        BackgroundJobFinishResult(
            session_id="chat-1",
            pid=9,
            command="bad",
            status="exited",
            exit_code=2,
            error_category=None,
        ),
        "en",
    )
    assert "exit_code=2" in msg


@pytest.mark.asyncio
async def test_resolve_user_locale_from_personal_settings() -> None:
    configs = MagicMock()
    configs.personal_settings_dict = {"locale": "zh-CN"}

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=configs),
    ):
        locale = await _resolve_user_locale()

    assert "zh" in locale.lower()


@pytest.mark.asyncio
async def test_resolve_user_locale_falls_back_to_language_key() -> None:
    configs = MagicMock()
    configs.personal_settings_dict = {"language": "en-US"}

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=configs),
    ):
        locale = await _resolve_user_locale()

    assert locale.startswith("en")


@pytest.mark.asyncio
async def test_resolve_user_locale_on_load_failure() -> None:
    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(side_effect=RuntimeError("config unavailable")),
    ):
        locale = await _resolve_user_locale()

    assert locale


@pytest.mark.asyncio
async def test_handler_ignores_missing_session_id() -> None:
    handler = ServerBackgroundJobFinishHandler()
    result = BackgroundJobFinishResult(
        session_id="",
        pid=1,
        command="x",
        status="exited",
        exit_code=0,
        error_category=None,
    )

    with patch(
        "app.services.agent.background_job_finish_handler.ChatService.append_message",
        AsyncMock(),
    ) as mock_append:
        await handler.on_background_job_finish(result)

    mock_append.assert_not_called()


@pytest.mark.asyncio
async def test_process_logs_exception_without_raising() -> None:
    handler = ServerBackgroundJobFinishHandler()
    result = BackgroundJobFinishResult(
        session_id="chat-x",
        pid=11,
        command="fail",
        status="exited",
        exit_code=0,
        error_category=None,
    )

    with (
        patch(
            "app.services.agent.background_job_finish_handler._resolve_user_locale",
            AsyncMock(return_value="en"),
        ),
        patch(
            "app.services.agent.background_job_finish_handler.ChatService.append_message",
            AsyncMock(side_effect=RuntimeError("db")),
        ),
        patch(
            "app.services.agent.background_job_finish_handler.get_event_bus",
            return_value=MagicMock(),
        ),
    ):
        await handler._process(result)


@pytest.mark.asyncio
async def test_finish_handler_dedupes_duplicate_pid() -> None:
    handler = ServerBackgroundJobFinishHandler()
    result = BackgroundJobFinishResult(
        session_id="chat-dedupe",
        pid=99,
        command="npm test",
        status="exited",
        exit_code=0,
        error_category=None,
        job_id=_TEST_JOB_ID,
    )

    with (
        patch(
            "app.services.agent.background_job_finish_handler._resolve_user_locale",
            AsyncMock(return_value="en"),
        ),
        patch(
            "app.services.agent.background_job_finish_handler.ChatService.append_message",
            AsyncMock(),
        ) as mock_append,
        patch(
            "app.services.agent.background_job_finish_handler.get_event_bus",
            return_value=MagicMock(),
        ),
        patch(
            "app.services.agent.goal_wait_background_resume.maybe_resume_goal_after_background_job",
            AsyncMock(),
        ),
    ):
        await handler.on_background_job_finish(result)
        await handler.on_background_job_finish(result)

    mock_append.assert_awaited_once()
