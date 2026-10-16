"""Unit tests for kanban event publisher review notifications.

Covers the BACKGROUND_TASK_DONE payload that carries ``board_id`` so push
click-through can deep-link to the in-review column, the publication of
``pending_review`` / ``rejected`` notices for source-chat and /btw tasks, and the
task-level update whose detail is the reason for the task's current state.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import BlockKind, KanbanTask, TaskStatus

from app.services.kanban import event_publisher
from app.services.kanban.event_publisher import (
    _build_background_done_payload,
    emit_review_requested,
    emit_task_rejected,
    publish_task_event,
)


def _make_task(**overrides: object) -> KanbanTask:
    metadata = overrides.pop("metadata", None)
    if metadata is None:
        metadata = {"source_chat_id": "chat-1", "user_id": "u-1"}
    status = overrides.pop("status", TaskStatus.IN_REVIEW)
    return KanbanTask(
        task_id="t-1",
        board_id="b-1",
        title="Weekly report",
        status=status,  # type: ignore[arg-type]
        metadata=metadata,  # type: ignore[arg-type]
        **overrides,
    )


def test_build_payload_carries_board_id_and_review_status() -> None:
    payload = _build_background_done_payload(
        _make_task(),
        status="pending_review",
        result="draft ready",
    )
    assert payload is not None
    assert payload["board_id"] == "b-1"
    assert payload["task_id"] == "t-1"
    assert payload["status"] == "pending_review"
    assert payload["title"] == "Weekly report"
    assert payload["result"] == "draft ready"
    assert payload["chat_id"] == "chat-1"
    assert payload["source_chat_id"] == "chat-1"
    assert payload["user_id"] == "u-1"


def test_build_payload_none_without_delivery_target() -> None:
    payload = _build_background_done_payload(
        _make_task(metadata={}),
        status="pending_review",
        result="",
    )
    assert payload is None


def test_build_payload_btw_routes_channel_chat() -> None:
    payload = _build_background_done_payload(
        _make_task(
            metadata={
                "background_source": "btw",
                "channel": "telegram",
                "chat_id": "ch-9",
            }
        ),
        status="pending_review",
        result="ok",
    )
    assert payload is not None
    assert payload["board_id"] == "b-1"
    assert payload["channel"] == "telegram"
    assert payload["chat_id"] == "ch-9"
    assert payload["background_source"] == "btw"


def test_emit_review_requested_publishes_pending_review() -> None:
    task = _make_task()
    with patch.object(event_publisher, "_publish_background_done") as publish:
        emit_review_requested(task)
    publish.assert_called_once()
    payload = publish.call_args.args[0]
    assert payload["status"] == "pending_review"
    assert payload["board_id"] == "b-1"
    assert payload["chat_id"] == "chat-1"


def test_emit_task_rejected_publishes_rejected() -> None:
    task = _make_task(error="bad output")
    with patch.object(event_publisher, "_publish_background_done") as publish:
        emit_task_rejected(task)
    publish.assert_called_once()
    payload = publish.call_args.args[0]
    assert payload["status"] == "rejected"
    assert payload["board_id"] == "b-1"
    assert payload["result"] == "bad output"


STALE_RESULT = "Draft summary written by the first attempt"


def _published_task_event(action: str, task: KanbanTask) -> dict[str, str]:
    with patch.object(event_publisher, "get_event_bus") as get_bus:
        publish_task_event(action, task)
    get_bus.return_value.publish.assert_called_once()
    return get_bus.return_value.publish.call_args.args[0].data


def test_blocked_task_reports_its_reason_not_the_result_of_an_earlier_attempt() -> None:
    task = _make_task(
        status=TaskStatus.BLOCKED,
        block_kind=BlockKind.HUMAN,
        blocked_reason="Need your decision: Postgres or SQLite?",
        result=STALE_RESULT,
    )
    data = _published_task_event("task_blocked", task)
    assert data["detail"] == "Need your decision: Postgres or SQLite?"
    assert data["block_kind"] == "human"


def test_failed_task_reports_its_error_not_the_result_of_an_earlier_attempt() -> None:
    task = _make_task(status=TaskStatus.FAILED, error="Worker crashed: disk full", result=STALE_RESULT)
    assert _published_task_event("task_failed", task)["detail"] == "Worker crashed: disk full"


def test_failed_task_without_an_error_falls_back_to_its_result() -> None:
    task = _make_task(status=TaskStatus.FAILED, result="partial output")
    assert _published_task_event("task_failed", task)["detail"] == "partial output"


def test_completed_task_reports_its_result() -> None:
    task = _make_task(status=TaskStatus.COMPLETED, result="Report ready", error="earlier attempt failed")
    assert _published_task_event("task_completed", task)["detail"] == "Report ready"


def test_scheduled_block_is_published_with_its_kind_and_without_a_reason_to_show() -> None:
    task = _make_task(
        status=TaskStatus.BLOCKED,
        block_kind=BlockKind.SCHEDULED,
        blocked_reason="Transient error detected, auto-retry at 12:40 UTC",
    )
    data = _published_task_event("task_blocked", task)
    assert data["block_kind"] == "scheduled"
    assert "detail" not in data


@pytest.mark.parametrize(
    ("status", "block_kind", "expected_detail", "expected_kind"),
    [
        (TaskStatus.BLOCKED, BlockKind.HUMAN, "Need a decision", "human"),
        (TaskStatus.BLOCKED, BlockKind.SCHEDULED, None, "scheduled"),
        (TaskStatus.COMPLETED, None, "Report ready", None),
        (TaskStatus.READY, None, None, None),
    ],
)
def test_a_moved_card_reports_the_reason_for_the_column_it_landed_in(
    status: TaskStatus, block_kind: BlockKind | None, expected_detail: str | None, expected_kind: str | None
) -> None:
    task = _make_task(
        status=status, block_kind=block_kind, blocked_reason="Need a decision", result="Report ready", error="earlier failure"
    )
    data = _published_task_event("moved", task)
    assert data["status"] == status.value
    assert data.get("detail") == expected_detail
    assert data.get("block_kind") == expected_kind


def test_block_kind_left_on_a_task_that_is_no_longer_blocked_is_not_published() -> None:
    task = _make_task(status=TaskStatus.COMPLETED, block_kind=BlockKind.SCHEDULED, result="Report ready")
    assert "block_kind" not in _published_task_event("task_completed", task)


def test_an_update_that_is_not_an_outcome_carries_no_detail() -> None:
    task = _make_task(status=TaskStatus.RUNNING, result=STALE_RESULT)
    assert "detail" not in _published_task_event("task_started", task)
