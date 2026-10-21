"""Tests for the text an outbound channel receives for each configured event."""

from __future__ import annotations

from app.core.notifications.dispatcher import _format_message
from app.services.event.app_event_bus import AppEvent, AppEventType


class TestFormatMessage:
    """Verify _format_message covers all configured event templates."""

    def test_pairing_pending(self) -> None:
        event = AppEvent(
            event_type=AppEventType.PAIRING_PENDING,
            data={"channel": "telegram", "sender_id": "12345"},
        )
        result = _format_message(event)
        assert result is not None
        assert "[Myrm AI]" in result
        assert "telegram" in result
        assert "12345" in result

    def test_approval_required(self) -> None:
        event = AppEvent(
            event_type=AppEventType.APPROVAL_REQUIRED,
            data={"approval_id": "a1", "action_type": "file_write", "status": "PENDING", "severity": "high"},
        )
        result = _format_message(event)
        assert result is not None
        assert "file_write" in result
        assert "high" in result

    def test_health_alert(self) -> None:
        event = AppEvent(
            event_type=AppEventType.HEALTH_ALERT,
            data={
                "component": "llm_provider",
                "status": "fail",
                "message": "API key invalid",
                "detail": "",
                "fix_suggestion": "",
                "layer": "server",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "llm_provider" in result
        assert "API key invalid" in result

    def test_budget_alert(self) -> None:
        event = AppEvent(
            event_type=AppEventType.BUDGET_ALERT,
            data={
                "subtype": "budget_alert",
                "status": "warning",
                "today_cost": 8.5,
                "daily_limit": 10.0,
                "remaining": 1.5,
                "pct": 85.0,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "warning" in result
        assert "85.0%" in result

    def test_new_skill_draft(self) -> None:
        event = AppEvent(
            event_type=AppEventType.NEW_SKILL_DRAFT,
            data={"draft_id": "d1", "draft_type": "CAPTURED", "name": "deploy-react"},
        )
        result = _format_message(event)
        assert result is not None
        assert "deploy-react" in result
        assert "CAPTURED" in result

    def test_message_dead_lettered(self) -> None:
        event = AppEvent(
            event_type=AppEventType.MESSAGE_DEAD_LETTERED,
            data={"channel": "telegram", "error_reason": "timeout"},
        )
        result = _format_message(event)
        assert result is not None
        assert "telegram" in result
        assert "timeout" in result

    def test_channel_disconnected(self) -> None:
        event = AppEvent(
            event_type=AppEventType.CHANNEL_DISCONNECTED,
            data={"channel": "wechat", "status": "error"},
        )
        result = _format_message(event)
        assert result is not None
        assert "wechat" in result

    def test_system_notification(self) -> None:
        event = AppEvent(
            event_type=AppEventType.SYSTEM_NOTIFICATION,
            data={"title": "Task Done", "message": "Report finished", "type": "info", "meta_data": {}},
        )
        result = _format_message(event)
        assert result is not None
        assert "Task Done" in result
        assert "Report finished" in result

    def test_goal_terminal_complete(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "goal_id": "g1",
                "session_id": "s1",
                "status": "complete",
                "objective": "Analyze user feedback",
                "files_modified": 3,
                "turns_used": 7,
                "execution_duration_s": 42.5,
                "total_tokens": 12450,
                "total_cost_usd": 0.0832,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "[Myrm AI] Goal complete: Analyze user feedback" in result
        assert "3 files" in result
        assert "7 turns" in result
        assert "42s" in result
        assert "12,450 tokens" in result
        assert "$0.08" in result

    def test_goal_terminal_cancelled(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "goal_id": "g2",
                "session_id": "s2",
                "status": "cancelled",
                "objective": "Deploy service",
                "files_modified": 0,
                "turns_used": 2,
                "execution_duration_s": 8.0,
                "total_tokens": 500,
                "total_cost_usd": 0.0,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "Goal cancelled" in result
        assert "0 files" in result
        assert "2 turns" in result
        assert "8s" in result
        assert "500 tokens" in result
        assert "$0.00" in result

    def test_goal_terminal_budget_limited(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "goal_id": "g3",
                "session_id": "s3",
                "status": "budget_limited",
                "objective": "Large analysis",
                "files_modified": 10,
                "turns_used": 25,
                "execution_duration_s": 180.3,
                "total_tokens": 100000,
                "total_cost_usd": 5.1234,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "Goal budget_limited" in result
        assert "10 files" in result
        assert "25 turns" in result
        assert "180s" in result
        assert "100,000 tokens" in result
        assert "$5.12" in result

    def test_goal_dequeued(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_DEQUEUED,
            data={
                "goal_id": "g4",
                "session_id": "s4",
                "objective": "Next task in queue",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "[Myrm AI] Next goal started: Next task in queue" in result

    def test_goal_terminal_missing_field_returns_none(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "goal_id": "g5",
                "session_id": "s5",
                "status": "complete",
                "objective": "Missing stats",
            },
        )
        result = _format_message(event)
        assert result is None

    def test_subagent_stale(self) -> None:
        event = AppEvent(
            event_type=AppEventType.SUBAGENT_STALE,
            data={
                "chat_id": "c1",
                "task_id": "t-stale",
                "agent_type": "researcher",
                "stale_duration_seconds": 310.0,
                "wasted_tokens": 4500,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "[Myrm AI]" in result
        assert "researcher" in result
        assert "t-stale" in result
        assert "310" in result
        assert "4,500" in result

    def test_subagent_stale_missing_field_returns_none(self) -> None:
        event = AppEvent(
            event_type=AppEventType.SUBAGENT_STALE,
            data={"chat_id": "c2", "task_id": "t2"},  # missing agent_type, etc.
        )
        assert _format_message(event) is None

    def test_unregistered_event_returns_none(self) -> None:
        event = AppEvent(
            event_type=AppEventType.IDLE_STATUS,
            data={"session_id": "s1", "status": "running"},
        )
        assert _format_message(event) is None

    def test_missing_template_field_returns_none(self) -> None:
        event = AppEvent(
            event_type=AppEventType.PAIRING_PENDING,
            data={"channel": "telegram"},  # missing sender_id
        )
        assert _format_message(event) is None
