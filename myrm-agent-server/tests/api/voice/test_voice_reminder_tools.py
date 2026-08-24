"""Unit and integration tests for Voice-Native Reminder tools (set_reminder, cancel_reminder, list_reminders).

Validates:
1. Realtime & Gemini Live function declarations include reminder tools.
2. Direct execution via BACKGROUND_TOOL_HANDLERS creates/cancels/lists JobType.REMINDER cron jobs.
3. Push notification emits voice_background_task_done for duplex voice announce.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.types import CronJob, JobStatus, JobType, Schedule, ScheduleKind

from app.api.voice.realtime import RealtimeToolExecRequest
from app.api.voice.realtime_background import BACKGROUND_TOOL_HANDLERS
from app.api.voice.tool_catalog import build_realtime_tools
from app.api.voice.voice_memory_context import VoiceMemoryContext
from app.core.cron.push_store import PushLevel, push


@pytest.mark.asyncio
async def test_realtime_tool_catalog_includes_reminder_tools():
    """Verify set_reminder, cancel_reminder, list_reminders are always declared in Realtime tools."""
    ctx = VoiceMemoryContext(enable_memory=True, allow_wiki=True, allow_sessions=True)
    tools = build_realtime_tools(enabled_builtin_tools=(), memory_context=ctx)
    tool_names = {t.name for t in tools}

    assert "set_reminder" in tool_names
    assert "cancel_reminder" in tool_names
    assert "list_reminders" in tool_names


@pytest.mark.asyncio
async def test_gemini_live_includes_reminder_tools():
    """Verify Gemini Live tool declarations include reminder tools."""
    from app.api.voice.gemini_live import _build_gemini_tools

    ctx = VoiceMemoryContext(enable_memory=True, allow_wiki=False, allow_sessions=False)
    tools = _build_gemini_tools(enabled_builtin_tools=(), memory_context=ctx)
    tool_names = {t.name for t in tools}

    assert "set_reminder" in tool_names
    assert "cancel_reminder" in tool_names
    assert "list_reminders" in tool_names


@pytest.mark.asyncio
async def test_set_reminder_execution_relative_minutes():
    """Test set_reminder with relative minutes_later param."""
    set_reminder_handler = BACKGROUND_TOOL_HANDLERS["set_reminder"]

    mock_job = CronJob(
        id="cron-reminder-123",
        user_id="default",
        name="Voice Reminder: drink water",
        job_type=JobType.REMINDER,
        schedule=Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(timezone.utc)),
        prompt="drink water",
    )

    mock_mgr = AsyncMock()
    mock_mgr.create_job.return_value = mock_job

    with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mock_mgr):
        req = RealtimeToolExecRequest(
            tool_name="set_reminder",
            arguments={"content": "drink water", "minutes_later": 10},
            chat_id="chat-test-voice-1",
        )
        resp = await set_reminder_handler(req)

        assert resp.error is None
        assert resp.result is not None
        data = json.loads(resp.result)
        assert data["success"] is True
        assert data["job_id"] == "cron-reminder-123"
        assert data["content"] == "drink water"

        mock_mgr.create_job.assert_awaited_once()
        call_kwargs = mock_mgr.create_job.call_args.kwargs
        assert call_kwargs["job_type"] == JobType.REMINDER
        assert call_kwargs["prompt"] == "drink water"
        assert call_kwargs["chat_id"] == "chat-test-voice-1"


@pytest.mark.asyncio
async def test_cancel_and_list_reminders():
    """Test cancel_reminder and list_reminders execution."""
    cancel_handler = BACKGROUND_TOOL_HANDLERS["cancel_reminder"]
    list_handler = BACKGROUND_TOOL_HANDLERS["list_reminders"]

    mock_job = CronJob(
        id="cron-reminder-456",
        user_id="default",
        name="Voice Reminder: team standup",
        job_type=JobType.REMINDER,
        schedule=Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(timezone.utc)),
        prompt="team standup",
        status=JobStatus.ACTIVE,
    )

    mock_mgr = AsyncMock()
    mock_mgr.list_jobs.return_value = [mock_job]
    mock_mgr.delete_job.return_value = True

    with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mock_mgr):
        # 1. List reminders
        list_req = RealtimeToolExecRequest(
            tool_name="list_reminders",
            arguments={},
            chat_id="chat-test-voice-1",
        )
        list_resp = await list_handler(list_req)
        assert list_resp.error is None
        list_data = json.loads(list_resp.result)
        assert list_data["count"] == 1
        assert list_data["reminders"][0]["id"] == "cron-reminder-456"

        # 2. Cancel reminder by content match
        cancel_req = RealtimeToolExecRequest(
            tool_name="cancel_reminder",
            arguments={"content": "standup"},
            chat_id="chat-test-voice-1",
        )
        cancel_resp = await cancel_handler(cancel_req)
        assert cancel_resp.error is None
        cancel_data = json.loads(cancel_resp.result)
        assert cancel_data["cancelled"] is True
        assert cancel_data["job_id"] == "cron-reminder-456"
        mock_mgr.delete_job.assert_awaited_once_with("default", "cron-reminder-456")


@pytest.mark.asyncio
async def test_cron_push_triggers_system_notification_with_voice_bg_done():
    """Test push store emits SYSTEM_NOTIFICATION with kind=voice_background_task_done."""
    from app.services.event.app_event_bus import AppEventType, get_event_bus

    bus = get_event_bus()
    q = bus.subscribe()

    try:
        await push(
            user_id="default",
            job_name="Voice Reminder: Drink Water",
            text="[Voice Reminder: Drink Water] Drink water now",
            level=PushLevel.SUCCESS,
            chat_id="chat-voice-777",
        )

        events = []
        while not q.empty():
            events.append(q.get_nowait())

        cron_events = [e for e in events if e.event_type == AppEventType.CRON_UPDATED]
        sys_events = [e for e in events if e.event_type == AppEventType.SYSTEM_NOTIFICATION]

        assert len(cron_events) >= 1
        assert len(sys_events) >= 1

        sys_event = sys_events[0]
        assert sys_event.data["meta_data"]["kind"] == "voice_background_task_done"
        assert sys_event.data["meta_data"]["chat_id"] == "chat-voice-777"
        assert sys_event.data["meta_data"]["source"] == "cron_reminder"
    finally:
        bus.unsubscribe(q)
