"""Unit tests for kanban event publisher review notifications.

Covers the BACKGROUND_TASK_DONE payload that carries ``board_id`` so push
click-through can deep-link to the in-review column, and the publication of
``pending_review`` / ``rejected`` notices for source-chat and /btw tasks.
"""

from __future__ import annotations

from unittest.mock import patch

from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.services.kanban import event_publisher
from app.services.kanban.event_publisher import (
    _build_background_done_payload,
    emit_review_requested,
    emit_task_rejected,
)


def _make_task(**overrides: object) -> KanbanTask:
    metadata = overrides.pop("metadata", None)
    if metadata is None:
        metadata = {"source_chat_id": "chat-1", "user_id": "u-1"}
    return KanbanTask(
        task_id="t-1",
        board_id="b-1",
        title="Weekly report",
        status=TaskStatus.IN_REVIEW,
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
