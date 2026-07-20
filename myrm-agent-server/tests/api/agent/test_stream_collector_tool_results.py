"""Unit tests for StreamContentCollector kanban/cron tool result persistence."""

import json

from app.services.agent.streaming_support.stream_collector import StreamContentCollector


def test_stream_collector_persists_kanban_add_task_result() -> None:
    collector = StreamContentCollector()

    collector.feed_event(
        {
            "type": "tool_end",
            "tool_name": "kanban_add_task",
            "result": json.dumps(
                {
                    "status": "added",
                    "task": {
                        "task_id": "task-abc",
                        "title": "Weekly report",
                        "board_id": "board-1",
                        "status": "ready",
                    },
                }
            ),
        }
    )

    extra_data = collector.extra_data

    assert extra_data is not None
    assert extra_data["kanban_tasks_created"] == [
        {
            "task_id": "task-abc",
            "title": "Weekly report",
            "board_id": "board-1",
        }
    ]


def test_stream_collector_appends_multiple_kanban_tasks() -> None:
    collector = StreamContentCollector()

    for idx in range(2):
        collector.feed_event(
            {
                "type": "tool_end",
                "tool_name": "kanban_add_task",
                "result": {
                    "status": "added",
                    "task": {
                        "task_id": f"task-{idx}",
                        "title": f"Task {idx}",
                        "board_id": "board-1",
                    },
                },
            }
        )

    extra_data = collector.extra_data

    assert extra_data is not None
    assert len(extra_data["kanban_tasks_created"]) == 2


def test_stream_collector_ignores_kanban_add_task_errors() -> None:
    collector = StreamContentCollector()

    collector.feed_event(
        {
            "type": "tool_end",
            "tool_name": "kanban_add_task",
            "result": json.dumps({"error": "board_id is required"}),
        }
    )

    assert collector.extra_data is None


def test_stream_collector_persists_cron_manage_success() -> None:
    collector = StreamContentCollector()

    collector.feed_event(
        {
            "type": "tool_end",
            "tool_name": "cron_manage",
            "result": {
                "status": "success",
                "action": "add",
                "job_id": "job-1",
                "name": "Daily sync",
                "job_type": "cron",
                "model": None,
                "schedule": "0 9 * * *",
                "next_run": "2026-07-21T09:00:00Z",
            },
        }
    )

    extra_data = collector.extra_data

    assert extra_data is not None
    assert extra_data["cron_job_result"]["job_id"] == "job-1"
    assert extra_data["cron_job_result"]["name"] == "Daily sync"
