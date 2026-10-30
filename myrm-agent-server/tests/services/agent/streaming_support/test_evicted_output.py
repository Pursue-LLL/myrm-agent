"""Evicted tool output: which progress step a stored stdout/stderr file belongs to, and what the step records about it."""

from __future__ import annotations

from app.services.agent.streaming_support.evicted_output import (
    BASH_EXECUTE_TOOL,
    attach_evicted_to_step,
    find_step_for_evicted,
    parse_evicted_ref_payload,
    step_accepts_pending_evicted,
)


def test_a_preview_longer_than_the_cap_is_cut_and_a_blank_one_is_dropped() -> None:
    long_preview = parse_evicted_ref_payload({"evicted_ref": "r", "preview_stdout": "x" * 9000}, {})
    blank_preview = parse_evicted_ref_payload({"evicted_ref": "r", "preview_stdout": "   "}, {})

    assert long_preview is not None
    assert blank_preview is not None
    assert long_preview["preview_stdout"] == "x" * 8000
    assert "preview_stdout" not in blank_preview


def test_the_tool_name_comes_from_the_payload_first_and_from_the_event_otherwise() -> None:
    from_payload = parse_evicted_ref_payload({"evicted_ref": "r", "tool_name": " bash "}, {"tool_name": "other"})
    from_event = parse_evicted_ref_payload("ref", {"tool_name": " other "})

    assert from_payload == {"evicted_ref": "r", "tool_name": "bash"}
    assert from_event == {"evicted_ref": "ref", "tool_name": "other"}


def test_a_payload_without_a_file_reference_is_rejected() -> None:
    assert parse_evicted_ref_payload({"tool_name": "bash"}, {}) is None


def test_an_evicted_reference_without_a_file_changes_nothing() -> None:
    step: dict[str, object] = {"tool_name": BASH_EXECUTE_TOOL}

    attach_evicted_to_step(step, {"tool_call_id": "c1"})

    assert step == {"tool_name": BASH_EXECUTE_TOOL}


def test_an_evicted_stdout_keeps_the_output_the_step_has_and_marks_it_done() -> None:
    step: dict[str, object] = {"tool_name": BASH_EXECUTE_TOOL, "stdout": "kept"}

    attach_evicted_to_step(step, {"evicted_ref": "r", "tool_call_id": " c1 "})

    assert step["evicted_file_ref"] == "r"
    assert step["status"] == "success"
    assert step["stdout"] == "kept"
    assert step["tool_call_id"] == "c1"
    assert step["step_key"] == "bash_code_execute_tool_tool"


def test_an_evicted_stdout_does_not_replace_the_call_id_the_step_already_has() -> None:
    step: dict[str, object] = {"tool_name": "read_file", "tool_call_id": "c1"}

    attach_evicted_to_step(step, {"evicted_ref": "r", "tool_call_id": "c2"})

    assert step["tool_call_id"] == "c1"
    assert step["step_key"] == "read_file"


def test_an_evicted_stderr_is_recorded_without_touching_the_stdout_or_status() -> None:
    step: dict[str, object] = {"tool_name": BASH_EXECUTE_TOOL, "status": "running"}

    attach_evicted_to_step(
        step,
        {"evicted_ref": "r", "stream": "stderr", "stored_chars": 10, "total_lines": 2, "storage_truncated": True},
    )

    assert step["evicted_stderr_file_ref"] == "r"
    assert step["evicted_stderr_stored_chars"] == 10
    assert step["evicted_stderr_total_lines"] == 2
    assert step["evicted_stderr_storage_truncated"] is True
    assert step["status"] == "running"
    assert "stdout" not in step


def test_the_file_goes_to_the_step_with_the_same_call_id_before_any_other_match() -> None:
    steps: list[dict[str, object]] = [{"tool_call_id": "c1"}, {"tool_name": BASH_EXECUTE_TOOL}]

    assert find_step_for_evicted(steps, {"evicted_ref": "r", "tool_call_id": "c1"}) is steps[0]


def test_the_file_goes_to_the_latest_step_of_that_tool_that_has_no_file_yet() -> None:
    steps: list[dict[str, object]] = [
        {"tool_name": "read_file"},
        {"tool_name": "read_file", "evicted_file_ref": "old"},
        {"tool_name": "read_file"},
    ]

    assert find_step_for_evicted(steps, {"evicted_ref": "r", "tool_name": "read_file"}) is steps[2]


def test_a_file_that_names_no_tool_goes_to_the_latest_shell_step_without_a_file() -> None:
    steps: list[dict[str, object]] = [
        {"tool_name": BASH_EXECUTE_TOOL, "evicted_file_ref": "old"},
        {"tool_name": BASH_EXECUTE_TOOL},
        {"tool_name": "read_file"},
    ]

    assert find_step_for_evicted(steps, {"evicted_ref": "r"}) is steps[1]
    assert find_step_for_evicted([{"tool_name": "read_file"}], {"evicted_ref": "r"}) is None


def test_a_step_takes_a_file_that_arrived_early_when_the_call_id_or_tool_matches() -> None:
    step: dict[str, object] = {"tool_name": "read_file", "tool_call_id": "c1"}

    assert step_accepts_pending_evicted(step, {"tool_call_id": "c1"})
    assert not step_accepts_pending_evicted(step, {"tool_call_id": "c2"})
    assert step_accepts_pending_evicted(step, {"tool_name": "read_file"})
    assert not step_accepts_pending_evicted(step, {"tool_name": "other"})


def test_a_file_that_names_neither_call_nor_tool_is_taken_only_by_a_shell_step() -> None:
    assert step_accepts_pending_evicted({"tool_name": BASH_EXECUTE_TOOL}, {})
    assert step_accepts_pending_evicted({"step_key": "bash_code_execute_tool_tool"}, {})
    assert not step_accepts_pending_evicted({"tool_name": "read_file", "step_key": "read_file"}, {})
