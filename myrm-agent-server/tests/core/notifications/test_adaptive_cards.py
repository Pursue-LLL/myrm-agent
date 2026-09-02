"""Unit tests for AdaptiveCardFormatter in app.core.notifications.adaptive_cards."""

from __future__ import annotations

from app.channels.types.components import ActionButton, ButtonStyle
from app.core.notifications.adaptive_cards import (
    FormattedNotification,
    format_legacy_text,
    format_notification,
)
from app.services.event.app_event_bus import AppEvent, AppEventType


def test_approval_required_adaptive_card() -> None:
    event = AppEvent(
        event_type=AppEventType.APPROVAL_REQUIRED,
        data={
            "approval_id": "appr_123",
            "action_type": "delete_database",
            "severity": "critical",
            "description": "Drop table users in prod",
        },
    )
    res = format_notification(event)
    assert res is not None
    assert isinstance(res, FormattedNotification)
    assert "Approval Required: delete_database" in res.content
    assert "critical" in res.content
    assert "Drop table users in prod" in res.content

    # Validate action buttons
    assert len(res.components) == 1
    row = res.components[0]
    assert len(row) == 2
    approve_btn, reject_btn = row
    assert isinstance(approve_btn, ActionButton)
    assert approve_btn.label == "Approve"
    assert approve_btn.action_id == "approval:approve:appr_123"
    assert approve_btn.style == ButtonStyle.PRIMARY

    assert isinstance(reject_btn, ActionButton)
    assert reject_btn.label == "Reject"
    assert reject_btn.action_id == "approval:reject:appr_123"
    assert reject_btn.style == ButtonStyle.DANGER


def test_pairing_pending_adaptive_card() -> None:
    event = AppEvent(
        event_type=AppEventType.PAIRING_PENDING,
        data={"channel": "telegram", "sender_id": "tg_user_999"},
    )
    res = format_notification(event)
    assert res is not None
    assert "New Pairing Request" in res.content
    assert "telegram" in res.content
    assert "tg_user_999" in res.content

    assert len(res.components) == 1
    row = res.components[0]
    assert len(row) == 2
    approve_btn, block_btn = row
    assert approve_btn.action_id == "pairing:approve:telegram:tg_user_999"
    assert block_btn.action_id == "pairing:block:telegram:tg_user_999"


def test_goal_terminal_adaptive_card() -> None:
    event = AppEvent(
        event_type=AppEventType.GOAL_TERMINAL,
        data={
            "status": "completed",
            "objective": "Implement notifications bridge",
            "files_modified": 4,
            "turns_used": 12,
            "execution_duration_s": 45.2,
            "total_tokens": 15200,
            "total_cost_usd": 0.08,
            "session_id": "sess_abc",
        },
    )
    res = format_notification(event)
    assert res is not None
    assert "Goal Completed" in res.content
    assert "4 files · 12 turns · 45s · 15,200 tokens · $0.08" in res.content

    assert len(res.components) == 1
    view_btn = res.components[0][0]
    assert isinstance(view_btn, ActionButton)
    assert view_btn.label == "View Session"
    assert view_btn.action_id == "session:view:sess_abc"


def test_background_task_done_adaptive_card() -> None:
    event = AppEvent(
        event_type=AppEventType.BACKGROUND_TASK_DONE,
        data={
            "task_id": "task_456",
            "status": "completed",
            "title": "Data Pipeline Sync",
            "summary": "1,000 records ingested without errors.",
            "board_id": "board_xyz",
        },
    )
    res = format_notification(event)
    assert res is not None
    assert "Task Completed: Data Pipeline Sync" in res.content
    assert "1,000 records ingested without errors." in res.content

    assert len(res.components) == 1
    view_btn = res.components[0][0]
    assert isinstance(view_btn, ActionButton)
    assert view_btn.label == "View Kanban"
    assert view_btn.action_id == "kanban:view:board_xyz"


def test_session_completed_adaptive_card() -> None:
    event = AppEvent(
        event_type=AppEventType.SESSION_COMPLETED,
        data={
            "title": "Code Refactor Chat",
            "detail": "Refactoring finished cleanly.",
            "session_id": "chat_001",
        },
    )
    res = format_notification(event)
    assert res is not None
    assert "Session Completed: Code Refactor Chat" in res.content
    assert "Refactoring finished cleanly." in res.content
    assert len(res.components) == 1
    assert res.components[0][0].action_id == "session:view:chat_001"


def test_legacy_fallback_unhandled_events() -> None:
    event = AppEvent(
        event_type=AppEventType.HEALTH_ALERT,
        data={"component": "redis", "message": "Connection refused"},
    )
    legacy = format_legacy_text(event)
    assert legacy == "[Myrm AI] Health alert (redis): Connection refused"

    card = format_notification(event)
    assert card is not None
    assert card.content == legacy
    assert card.components == ()
