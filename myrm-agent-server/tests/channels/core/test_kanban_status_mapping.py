"""Unit tests for _kanban_status_to_bg_status — Kanban→BackgroundTask status mapping."""

from __future__ import annotations

import pytest

from app.core.channel_bridge.background_task_handler import _kanban_status_to_bg_status
from myrm_agent_harness.toolkits.kanban.types import TaskStatus


class TestKanbanStatusToBgStatus:
    """Tests for the _kanban_status_to_bg_status mapping function."""

    @pytest.mark.parametrize(
        "kanban_status, expected",
        [
            (TaskStatus.READY, "running"),
            (TaskStatus.RUNNING, "running"),
            (TaskStatus.BACKLOG, "running"),
            (TaskStatus.TRIAGE, "running"),
            (TaskStatus.COMPLETED, "completed"),
            (TaskStatus.ARCHIVED, "completed"),
            (TaskStatus.FAILED, "failed"),
            (TaskStatus.BLOCKED, "failed"),
        ],
    )
    def test_status_mapping_without_error(self, kanban_status: TaskStatus, expected: str) -> None:
        assert _kanban_status_to_bg_status(kanban_status) == expected

    def test_failed_with_timeout_error_returns_timed_out(self) -> None:
        error = "Task abc12345 timed out after 300s (limit 300s)"
        assert _kanban_status_to_bg_status(TaskStatus.FAILED, error) == "timed_out"

    def test_failed_with_non_timeout_error_returns_failed(self) -> None:
        error = "Tool execution raised RuntimeError: connection refused"
        assert _kanban_status_to_bg_status(TaskStatus.FAILED, error) == "failed"

    def test_failed_with_empty_error_returns_failed(self) -> None:
        assert _kanban_status_to_bg_status(TaskStatus.FAILED, "") == "failed"

    def test_failed_with_partial_timeout_string_returns_timed_out(self) -> None:
        assert _kanban_status_to_bg_status(TaskStatus.FAILED, "task timed out") == "timed_out"

    def test_blocked_with_timeout_error_returns_timed_out(self) -> None:
        """BLOCKED tasks caused by timeout still surface as timed_out — root cause wins."""
        error = "Task abc12345 timed out after 300s (limit 300s)"
        assert _kanban_status_to_bg_status(TaskStatus.BLOCKED, error) == "timed_out"

    def test_running_with_timeout_error_is_not_timed_out(self) -> None:
        """Non-terminal states never produce timed_out even with a stale timeout error."""
        error = "Task abc12345 timed out after 300s (limit 300s)"
        assert _kanban_status_to_bg_status(TaskStatus.RUNNING, error) == "running"

    def test_failed_with_cancelled_error_returns_cancelled(self) -> None:
        """User-cancelled tasks surface as 'cancelled' instead of generic 'failed'."""
        assert _kanban_status_to_bg_status(TaskStatus.FAILED, "Cancelled by user") == "cancelled"

    def test_blocked_with_cancelled_error_returns_cancelled(self) -> None:
        """BLOCKED tasks with cancellation error also surface as 'cancelled'."""
        assert _kanban_status_to_bg_status(TaskStatus.BLOCKED, "Cancelled by user") == "cancelled"

    def test_running_with_cancelled_error_is_not_cancelled(self) -> None:
        """Non-terminal states never produce cancelled even with a stale cancel error."""
        assert _kanban_status_to_bg_status(TaskStatus.RUNNING, "Cancelled by user") == "running"

    def test_unknown_status_falls_back_to_running(self) -> None:
        assert _kanban_status_to_bg_status("unknown_status") == "running"  # type: ignore[arg-type]
