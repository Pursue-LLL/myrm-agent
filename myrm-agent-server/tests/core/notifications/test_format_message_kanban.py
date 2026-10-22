"""Tests for the text an outbound channel receives when a kanban task update is worth a message."""

from __future__ import annotations

import pytest

from app.core.notifications.dispatcher import _format_message
from app.services.event.app_event_bus import AppEvent, AppEventType


class TestKanbanFormatMessage:
    """Verify which kanban task updates are sent to the owner's channels, and what they say."""

    def test_kanban_task_completed_from_dispatcher(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={
                "board_id": "b1",
                "task_id": "t1",
                "action": "task_completed",
                "title": "Write Report",
                "detail": "Report generated at /docs/report.pdf",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert '"Write Report" completed' in result
        assert "Report generated" in result

    def test_kanban_task_blocked_from_dispatcher(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={
                "board_id": "b1",
                "task_id": "t1",
                "action": "task_blocked",
                "title": "Deploy Service",
                "detail": "Auto-blocked after 3 failures",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert '"Deploy Service" blocked' in result
        assert "Auto-blocked" in result

    def test_kanban_task_failed_from_dispatcher(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "task_failed", "title": "Code Review"},
        )
        result = _format_message(event)
        assert result is not None
        assert '"Code Review" failed' in result

    def test_kanban_moved_to_completed(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={
                "board_id": "b1",
                "task_id": "t1",
                "action": "moved",
                "title": "Analysis",
                "status": "completed",
                "detail": "Done",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert '"Analysis" completed' in result

    def test_kanban_moved_to_ready_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "moved", "title": "Task", "status": "ready"},
        )
        assert _format_message(event) is None

    def test_kanban_created_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "created", "title": "New"},
        )
        assert _format_message(event) is None

    def test_kanban_deleted_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "deleted"},
        )
        assert _format_message(event) is None

    def test_kanban_detail_truncated(self) -> None:
        long_detail = "x" * 300
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "task_completed", "title": "LongTask", "detail": long_detail},
        )
        result = _format_message(event)
        assert result is not None
        assert len(result) < 250

    def test_kanban_moved_to_blocked(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={
                "board_id": "b1",
                "task_id": "t1",
                "action": "moved",
                "title": "BlockedTask",
                "status": "blocked",
                "detail": "Resource unavailable",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert '"BlockedTask" blocked' in result
        assert "Resource unavailable" in result

    def test_kanban_moved_to_failed(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "moved", "title": "FailedTask", "status": "failed"},
        )
        result = _format_message(event)
        assert result is not None
        assert '"FailedTask" failed' in result

    @pytest.mark.parametrize(
        "data",
        [
            {"action": "task_blocked", "block_kind": "scheduled"},
            {"action": "moved", "status": "blocked", "block_kind": "scheduled"},
        ],
    )
    def test_kanban_scheduled_block_skipped(self, data: dict[str, str]) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "title": "Nightly", "detail": "Transient error", **data},
        )
        assert _format_message(event) is None

    @pytest.mark.parametrize("block_kind", ["human", "external"])
    def test_kanban_block_waiting_for_someone_still_sent(self, block_kind: str) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={
                "board_id": "b1",
                "task_id": "t1",
                "action": "task_blocked",
                "title": "Release",
                "detail": "Need your decision",
                "block_kind": block_kind,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert '"Release" blocked' in result
        assert "Need your decision" in result

    def test_kanban_updated_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "updated", "title": "T"},
        )
        assert _format_message(event) is None

    def test_kanban_promoted_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "promoted"},
        )
        assert _format_message(event) is None

    def test_kanban_dependency_added_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "dependency_added"},
        )
        assert _format_message(event) is None

    def test_kanban_dependency_removed_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "dependency_removed"},
        )
        assert _format_message(event) is None

    def test_kanban_commented_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "commented"},
        )
        assert _format_message(event) is None

    def test_kanban_no_title_uses_task_id(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "abc123", "action": "task_completed"},
        )
        result = _format_message(event)
        assert result is not None
        assert '"abc123" completed' in result

    def test_kanban_empty_data_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={},
        )
        assert _format_message(event) is None

    def test_kanban_no_detail_no_suffix(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "task_completed", "title": "Clean", "detail": ""},
        )
        result = _format_message(event)
        assert result is not None
        assert result.endswith("completed")
        assert "\n" not in result

    def test_kanban_moved_to_running_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "moved", "title": "T", "status": "running"},
        )
        assert _format_message(event) is None

    def test_kanban_moved_to_backlog_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "moved", "title": "T", "status": "backlog"},
        )
        assert _format_message(event) is None
