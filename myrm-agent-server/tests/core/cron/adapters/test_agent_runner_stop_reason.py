"""Stop-reason extraction tests for cron agent runner stream accumulation."""

from __future__ import annotations

from app.core.cron.adapters.agent_runner import (
    _derive_stop_reason_from_event,
    _StreamAccumulator,
)


def test_derive_iteration_limit_stop_reason() -> None:
    reason = _derive_stop_reason_from_event(
        {
            "type": "iteration_limit_reached",
            "data": {
                "limit": 50,
                "nodes_completed": 50,
            },
        }
    )
    assert reason is not None
    assert reason["code"] == "iteration_limit_reached"
    assert reason["category"] == "limit"


def test_derive_engine_limit_stop_reason_from_tasks_steps_error() -> None:
    reason = _derive_stop_reason_from_event(
        {
            "type": "tasks_steps",
            "status": "error",
            "error": "Tool call limit exceeded (max_tool_calls=1)",
        }
    )
    assert reason is not None
    assert reason["code"] == "engine_limit_reached"
    assert reason["category"] == "limit"


def test_accumulator_persists_highest_priority_stop_reason() -> None:
    acc = _StreamAccumulator()
    acc.set_stop_reason(
        {
            "code": "error",
            "category": "error",
            "message": "unknown failure",
        }
    )
    acc.set_stop_reason(
        {
            "code": "iteration_limit_reached",
            "category": "limit",
            "message": "Iteration limit reached",
        }
    )
    result = acc.to_result(model="test-model")
    assert result.metadata is not None
    stop_reason = result.metadata.get("stopReason")
    assert isinstance(stop_reason, dict)
    assert stop_reason.get("code") == "iteration_limit_reached"
