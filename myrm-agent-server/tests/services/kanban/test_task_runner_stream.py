"""The kanban run result is the answer text minus any segment a recovery restarted."""

from __future__ import annotations

from app.services.kanban.task_runner.stream import _StreamAccumulator


def test_result_drops_the_segment_a_recovery_restarts() -> None:
    acc = _StreamAccumulator()
    for event in (
        {"type": "message", "data": "Let me check. "},
        {"type": "tool_start"},
        {"type": "message", "data": "The capital of France is Pa"},
        {"type": "status", "step_key": "model_failover", "restart": True},
        {"type": "message", "data": "Paris."},
    ):
        acc.add(event)

    assert acc.to_result() == (True, "Let me check. Paris.")


def test_an_error_event_still_fails_the_run() -> None:
    acc = _StreamAccumulator()
    acc.add({"type": "message", "data": "partial"})
    acc.add({"type": "error", "error": "boom", "error_type": "RuntimeError"})

    assert acc.to_result() == (False, "RuntimeError: boom")
