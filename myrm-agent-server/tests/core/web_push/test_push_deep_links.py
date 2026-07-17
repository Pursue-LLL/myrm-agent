"""Tests for resolve_push_url — Web Push click-through routing."""

from __future__ import annotations

from app.core.web_push.push_deep_links import resolve_push_url
from app.services.event.app_event_bus import AppEvent, AppEventType


class TestResolvePushUrl:
    def test_approval_required_uses_chat_id_with_query(self) -> None:
        event = AppEvent(
            event_type=AppEventType.APPROVAL_REQUIRED,
            data={
                "approval_id": "ap-deep-link-1",
                "chat_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "action_type": "delete_file",
                "severity": "high",
            },
        )
        assert (
            resolve_push_url(event)
            == "/a1b2c3d4-e5f6-7890-abcd-ef1234567890?approval=ap-deep-link-1"
        )

    def test_approval_required_without_approval_id_uses_chat_path_only(self) -> None:
        event = AppEvent(
            event_type=AppEventType.APPROVAL_REQUIRED,
            data={
                "chat_id": "chat-only-path",
                "action_type": "delete_file",
                "severity": "high",
            },
        )
        assert resolve_push_url(event) == "/chat-only-path"

    def test_goal_terminal_uses_session_id(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "goal_id": "g1",
                "session_id": "session-xyz",
                "status": "completed",
                "objective": "Ship feature",
            },
        )
        assert resolve_push_url(event) == "/session-xyz"

    def test_background_task_done_uses_chat_id(self) -> None:
        event = AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": "t1",
                "title": "Research",
                "chat_id": "btw-chat-99",
                "channel": "web",
            },
        )
        assert resolve_push_url(event) == "/btw-chat-99"

    def test_system_notification_reads_meta_data_chat_id(self) -> None:
        event = AppEvent(
            event_type=AppEventType.SYSTEM_NOTIFICATION,
            data={
                "title": "Job finished",
                "message": "Done",
                "meta_data": {"chat_id": "job-chat-7", "kind": "background_job_finish"},
            },
        )
        assert resolve_push_url(event) == "/job-chat-7"

    def test_health_alert_routes_to_system_settings(self) -> None:
        event = AppEvent(
            event_type=AppEventType.HEALTH_ALERT,
            data={"component": "llm", "message": "down"},
        )
        assert resolve_push_url(event) == "/settings/system"

    def test_budget_alert_routes_to_system_settings(self) -> None:
        event = AppEvent(
            event_type=AppEventType.BUDGET_ALERT,
            data={"status": "warning", "pct": 90, "today_cost": 1, "daily_limit": 2},
        )
        assert resolve_push_url(event) == "/settings/system"

    def test_channel_disconnected_routes_to_channels_settings(self) -> None:
        event = AppEvent(
            event_type=AppEventType.CHANNEL_DISCONNECTED,
            data={"channel": "telegram", "status": "offline"},
        )
        assert resolve_push_url(event) == "/settings/channels"

    def test_oauth_reauth_routes_to_integration_catalog(self) -> None:
        event = AppEvent(
            event_type=AppEventType.OAUTH_REAUTH_REQUIRED,
            data={"issuer": "google", "reason": "expired"},
        )
        assert resolve_push_url(event) == "/settings/integrationCatalog"

    def test_missing_chat_id_falls_back_to_home(self) -> None:
        event = AppEvent(
            event_type=AppEventType.APPROVAL_REQUIRED,
            data={"approval_id": "ap-2", "action_type": "x", "severity": "low"},
        )
        assert resolve_push_url(event) == "/"
