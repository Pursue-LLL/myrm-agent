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


def test_stream_collector_persists_evicted_stderr_stats_on_progress_step() -> None:
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
                "evicted_ref": "output_stderr_stats.txt",
                "stored_chars": 8192,
                "total_lines": 31000,
                "storage_truncated": True,
                "stream": "stderr",
            },
        }
    )
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and steps
    step = steps[-1]
    assert step.get("evicted_stderr_file_ref") == "output_stderr_stats.txt"
    assert step.get("evicted_stderr_stored_chars") == 8192
    assert step.get("evicted_stderr_total_lines") == 31000
    assert step.get("evicted_stderr_storage_truncated") is True
    assert step.get("evicted_file_ref") is None


def test_stream_collector_persists_dual_evicted_refs_on_same_step() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tasks_steps",
            "tool_call_id": "call_dual_1",
            "tool_name": "bash_code_execute_tool",
            "data": [{"status": "running"}],
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {
                "evicted_ref": "output_stdout.txt",
                "stored_chars": 50000,
                "total_lines": 1000,
                "stream": "stdout",
            },
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {
                "evicted_ref": "output_stderr.txt",
                "stored_chars": 30000,
                "total_lines": 600,
                "stream": "stderr",
            },
        }
    )
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 1
    step = steps[0]
    assert step.get("evicted_file_ref") == "output_stdout.txt"
    assert step.get("evicted_stored_chars") == 50000
    assert step.get("evicted_stderr_file_ref") == "output_stderr.txt"
    assert step.get("evicted_stderr_stored_chars") == 30000
    assert step.get("evicted_stderr_total_lines") == 600
    assert step.get("status") == "success"


def test_stream_collector_stderr_evicted_ref_finds_step_with_claimed_stdout() -> None:
    """Regression: stderr must attach to the same step already claiming stdout
    when matching falls back to tool_name (no tool_call_id present)."""
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_step_a",
            "tool_name": "bash_code_execute_tool",
            "data": [{"code": "pytest -v"}],
        }
    )
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_step_b",
            "tool_name": "bash_code_execute_tool",
            "data": [{"code": "second command"}],
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {"evicted_ref": "b_stdout.txt", "stream": "stdout"},
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {"evicted_ref": "b_stderr.txt", "stream": "stderr"},
        }
    )
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 2
    by_key = {step.get("step_key"): step for step in steps}
    b_step = by_key.get("bash_step_b")
    a_step = by_key.get("bash_step_a")
    assert b_step is not None and a_step is not None
    assert b_step.get("evicted_file_ref") == "b_stdout.txt"
    assert b_step.get("evicted_stderr_file_ref") == "b_stderr.txt"
    assert a_step.get("evicted_file_ref") is None
    assert a_step.get("evicted_stderr_file_ref") is None


def test_stream_collector_defers_stderr_evicted_ref_until_tasks_steps() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {"evicted_ref": "stderr_cafebabe.txt", "stream": "stderr"},
        }
    )
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "data": [{"code": "failing script"}],
        }
    )
    collector.feed_event({"type": "message_end"})
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 1
    step = steps[0]
    assert step.get("evicted_stderr_file_ref") == "stderr_cafebabe.txt"
    assert step.get("step_key") == "bash_code_execute_tool_tool"


def test_stream_collector_defers_dual_evicted_refs_without_losing_stdout() -> None:
    """Regression: pending evicted must keep both stdout and stderr when both
    arrive before the step is created (single-value pending would overwrite)."""
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {"evicted_ref": "pending_stdout.txt", "stream": "stdout"},
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {"evicted_ref": "pending_stderr.txt", "stream": "stderr"},
        }
    )
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool_tool",
            "tool_name": "bash_code_execute_tool",
            "data": [{"code": "failing script"}],
        }
    )
    collector.feed_event({"type": "message_end"})
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 1
    step = steps[0]
    assert step.get("evicted_file_ref") == "pending_stdout.txt"
    assert step.get("evicted_stderr_file_ref") == "pending_stderr.txt"


def test_stream_collector_flush_dual_pending_merges_into_one_fallback_step() -> None:
    """Regression: message_end flush with no steps must merge stdout+stderr
    pending into a single fallback step (stream-aware claim prevents split)."""
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {"evicted_ref": "fb_stdout.txt", "stream": "stdout"},
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {"evicted_ref": "fb_stderr.txt", "stream": "stderr"},
        }
    )
    collector.feed_event({"type": "message_end"})
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 1
    step = steps[0]
    assert step.get("evicted_file_ref") == "fb_stdout.txt"
    assert step.get("evicted_stderr_file_ref") == "fb_stderr.txt"


def test_stream_collector_pending_partial_match_keeps_unmatched_stream() -> None:
    """Regression: when a pending stdout claims an early step, a pending stderr
    with a different tool_call_id must stay pending for the later matching step."""
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {"evicted_ref": "p_stdout.txt", "stream": "stdout"},
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "tool_call_id": "call_b",
            "data": {
                "evicted_ref": "p_stderr.txt",
                "stream": "stderr",
                "tool_call_id": "call_b",
            },
        }
    )
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_step_a",
            "tool_name": "bash_code_execute_tool",
            "data": [{"code": "cmd a"}],
        }
    )
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_step_b",
            "tool_name": "bash_code_execute_tool",
            "tool_call_id": "call_b",
            "data": [{"code": "cmd b"}],
        }
    )
    collector.feed_event({"type": "message_end"})
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 2
    step_a = next(s for s in steps if s.get("step_key") == "bash_step_a")
    step_b = next(s for s in steps if s.get("step_key") == "bash_step_b")
    assert step_a.get("evicted_file_ref") == "p_stdout.txt"
    assert step_a.get("evicted_stderr_file_ref") is None
    assert step_b.get("evicted_stderr_file_ref") == "p_stderr.txt"
    assert step_b.get("evicted_file_ref") is None


def test_stream_collector_flush_distinct_tools_get_distinct_fallback_steps() -> None:
    """Regression: two different tools flushing pending get separate fallback
    steps (not merged), and each non-bash fallback gets its tool_name as step_key."""
    collector = StreamContentCollector()
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "bash_code_execute_tool",
            "data": {"evicted_ref": "bash_out.txt", "stream": "stdout"},
        }
    )
    collector.feed_event(
        {
            "type": "tool_evicted_ref",
            "tool_name": "web_fetch_tool",
            "data": {"evicted_ref": "webfetch_out.txt", "stream": "stdout"},
        }
    )
    collector.feed_event({"type": "message_end"})
    extra = collector.extra_data
    assert extra is not None
    steps = extra.get("progressSteps")
    assert isinstance(steps, list) and len(steps) == 2
    bash_step = next(s for s in steps if s.get("tool_name") == "bash_code_execute_tool")
    wf_step = next(s for s in steps if s.get("tool_name") == "web_fetch_tool")
    assert bash_step.get("evicted_file_ref") == "bash_out.txt"
    assert bash_step.get("step_key") == "bash_code_execute_tool_tool"
    assert wf_step.get("evicted_file_ref") == "webfetch_out.txt"
    assert wf_step.get("step_key") == "web_fetch_tool"


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


def test_stream_collector_persists_guardrail_blocked_error_category_on_tasks_steps() -> (
    None
):
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
