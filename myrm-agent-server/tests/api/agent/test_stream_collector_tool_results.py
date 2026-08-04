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


def test_stream_collector_persists_evicted_stats_on_progress_step() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tasks_steps",
            "tool_name": "bash_code_execute_tool",
            "data": [{"status": "running"}],
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {
                "evicted_ref": "output_stats.txt",
                "stored_chars": 4096,
                "total_lines": 25000,
                "storage_truncated": True,
            },
        }
    )
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and steps
    step = steps[-1]
    assert step.get("evicted_file_ref") == "output_stats.txt"
    assert step.get("evicted_stored_chars") == 4096
    assert step.get("evicted_total_lines") == 25000
    assert step.get("evicted_storage_truncated") is True


def test_stream_collector_persists_tool_evicted_ref_on_progress_step() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tasks_steps",
            "tool_name": "bash_code_execute_tool",
            "data": [{"status": "running"}],
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": "output_deadbeef.txt",
        }
    )
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and steps
    assert steps[-1].get("evicted_file_ref") == "output_deadbeef.txt"
    assert "LARGE OUTPUT TRUNCATED" in str(steps[-1].get("stdout") or "")


def test_stream_collector_defers_evicted_ref_until_tasks_steps() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "data": "output_cafebabe.txt",
        }
    )
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "data": [{"code": "echo hi"}],
        }
    )
    collector.feed_event({"type": "message_end"})
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 1
    step = steps[0]
    assert step.get("evicted_file_ref") == "output_cafebabe.txt"
    assert step.get("step_key") == "bash_code_execute_tool_tool"


def test_stream_collector_binds_evicted_ref_by_tool_call_id() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "tool_call_id": "call_evict_1",
            "data": [{"code": "seq 1 25000"}],
        }
    )
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "tool_call_id": "call_evict_2",
            "data": [{"code": "echo second"}],
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "data": {
                "evicted_ref": "output_deadbeef.txt",
                "tool_call_id": "call_evict_1",
                "preview_stdout": "[LARGE OUTPUT TRUNCATED]\nline-25000",
            },
        }
    )
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 2
    first = steps[0]
    second = steps[1]
    assert first.get("tool_call_id") == "call_evict_1"
    assert first.get("evicted_file_ref") == "output_deadbeef.txt"
    assert "line-25000" in str(first.get("stdout") or "")
    assert second.get("evicted_file_ref") is None


def test_stream_collector_merges_duplicate_tool_call_id_tasks_steps() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "tool_call_id": "call_merge_1",
            "data": [{"code": "echo hi"}],
        }
    )
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "tool_call_id": "call_merge_1",
            "data": [{"code": "echo hi"}],
            "status": "success",
        }
    )
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 1
    assert steps[0].get("tool_call_id") == "call_merge_1"
    assert steps[0].get("status") == "success"


def test_stream_collector_persists_tool_stdout_chunks_on_progress_step() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tasks_steps",
            "tool_name": "bash_code_execute_tool",
            "data": [{"status": "running"}],
        }
    )
    collector.feed_event(
        {
            "type": "tool_stdout_chunk",
            "tool_name": "bash_code_execute_tool",
            "data": "line-1\n",
        }
    )
    collector.feed_event(
        {
            "type": "tool_stdout_chunk",
            "tool_name": "bash_code_execute_tool",
            "data": "line-2\n",
        }
    )
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and steps
    assert steps[-1].get("stdout") == "line-1\nline-2\n"


def test_stream_collector_persists_guardrail_blocked_error_category_on_tasks_steps() -> None:
    """Regression: bash myrm_tools preflight must keep error_category for ProgressSteps Badge."""
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "tool_call_id": "call_guardrail_1",
            "status": "error",
            "error": "Command blocked: import myrm_tools",
            "error_category": "guardrail_blocked",
            "data": [{"code": "import myrm_tools"}],
        }
    )

    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 1
    step = steps[0]
    assert step.get("tool_call_id") == "call_guardrail_1"
    assert step.get("status") == "error"
    assert step.get("error_category") == "guardrail_blocked"


def test_stream_collector_merges_guardrail_error_category_by_tool_call_id() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "tool_call_id": "call_guardrail_merge",
            "status": "running",
            "data": [{"code": "import myrm_tools"}],
        }
    )
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "tool_call_id": "call_guardrail_merge",
            "status": "error",
            "error": "Command blocked: import myrm_tools",
            "error_category": "guardrail_blocked",
            "data": [{"code": "import myrm_tools"}],
        }
    )

    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 1
    assert steps[0].get("error_category") == "guardrail_blocked"
    assert steps[0].get("status") == "error"
