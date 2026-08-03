from app.services.agent.streaming_support.stream_collector_helpers import (
    collect_clarification_required,
    collect_file_mutation_failures,
    collect_plan_confirmation_status,
)


def test_collect_clarification_required_deep_research_source() -> None:
    payload = collect_clarification_required(
        {
            "type": "clarification_required",
            "data": {
                "type": "ask_question",
                "source": "deep_research",
                "form": {
                    "questions": [{"id": "q1", "prompt": "Which one?"}],
                },
            },
        }
    )
    assert payload is not None
    assert payload["isResumeMode"] is False
    assert payload["answered"] is False


def test_collect_plan_confirmation_waiting() -> None:
    payload = collect_plan_confirmation_status(
        {
            "phase": "plan_confirm",
            "status": "waiting",
            "plan": "Step 1",
        }
    )
    assert payload is not None
    assert payload["status"] == "waiting"
    assert payload["source"] == "deep_research"


def test_collect_plan_confirmation_dynamic_workflow() -> None:
    payload = collect_plan_confirmation_status(
        {
            "phase": "plan_confirm",
            "status": "waiting",
            "plan": "Detected 2 literal spawn call(s)",
            "source": "dynamic_workflow",
            "spawn_count": 2,
            "estimated_cost_usd": 1.25,
        }
    )
    assert payload is not None
    assert payload["source"] == "dynamic_workflow"
    assert payload["spawnCount"] == 2
    assert payload["estimatedCostUsd"] == 1.25


def test_collect_file_mutation_failures_normalizes_rows() -> None:
    target: list[dict[str, object]] = []
    collect_file_mutation_failures(
        target,
        {
            "files": [
                {
                    "path": " empty_write_e2e.txt ",
                    "tool": " file_write_tool ",
                    "error_preview": "Cannot write empty file content",
                },
                {
                    "path": "bad.py",
                    "tool": "file_edit_tool",
                    "error_preview": 123,
                },
            ]
        },
    )
    assert len(target) == 2
    assert target[0]["path"] == "empty_write_e2e.txt"
    assert target[0]["tool"] == "file_write_tool"
    assert target[1]["error_preview"] == ""


def test_collect_file_mutation_failures_skips_invalid_payload() -> None:
    target: list[dict[str, object]] = []
    collect_file_mutation_failures(target, "not-a-dict")
    collect_file_mutation_failures(target, {"files": "bad"})
    collect_file_mutation_failures(
        target,
        {
            "files": [
                "not-a-row",
                {"path": "", "tool": "file_write_tool"},
                {"path": "ok.txt", "tool": ""},
            ]
        },
    )
    assert target == []
