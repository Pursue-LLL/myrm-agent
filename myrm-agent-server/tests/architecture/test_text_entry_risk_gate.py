"""Architecture test: every entry that takes text a user typed for an agent to act on screens it first.

A secret that gets past one entry is stored (a cron prompt, a task card) or delivered (a steer) as if no rule existed.
Each entry below must call the gate that fits it, and every gate must end in ``screen_user_text``, the single place
that decides, records and fails closed. An endpoint that accepts task-instruction text of a user belongs in this table.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[2] / "app"

# (file under app/, function that receives the text, the gate it must call)
_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("services/agent/stream_session/orchestrator.py", "run_agent_stream", "check_stream_risk"),
    ("api/agents/general_agent/streaming.py", "steer_agent", "_risk_refusal"),
    ("api/agents/general_agent/streaming.py", "redirect_agent", "_risk_refusal"),
    ("api/agents/subagents.py", "steer_subagent", "reject_if_risky"),
    ("api/background_tasks/router.py", "steer_background_task", "reject_if_risky"),
    ("api/cron/routes/jobs.py", "create_job", "reject_if_risky"),
    ("api/cron/routes/jobs.py", "update_job", "reject_if_risky"),
    ("api/cron/routes/heartbeat.py", "heartbeat_enable", "reject_if_risky"),
    ("api/kanban/routes/tasks.py", "create_task", "reject_if_risky"),
    ("api/kanban/routes/tasks.py", "update_task", "reject_if_risky"),
    ("api/kanban/routes/task_meta.py", "add_comment", "reject_if_risky"),
    ("api/goals/constraints.py", "update_goal_constraints", "reject_if_risky"),
    ("api/goals/constraints.py", "update_goal_objective", "reject_if_risky"),
    ("channels/routing/router.py", "_consume_loop", "hold_risky_inbound"),
    ("channels/routing/router.py", "_dispatch_resolved", "hold_risky_inbound"),
    ("channels/routing/router.py", "_handle_merged", "hold_risky_inbound"),
)

# Each gate is a thin wrapper that must end in the one screening entry.
_WRAPPERS: tuple[tuple[str, str], ...] = (
    ("services/agent/stream_session/risk_gate.py", "check_stream_risk"),
    ("api/agents/general_agent/streaming.py", "_risk_refusal"),
    ("services/risk/refusal.py", "reject_if_risky"),
    ("channels/routing/inbound_risk_gate.py", "hold_risky_inbound"),
)
_SCREEN = "screen_user_text"


def _is_name(node: ast.expr, name: str) -> bool:
    return (isinstance(node, ast.Name) and node.id == name) or (isinstance(node, ast.Attribute) and node.attr == name)


def function_calls(source: str, function: str, callee: str) -> bool | None:
    """Whether *function* in *source* calls *callee*; None when the source defines no such function."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function:
            return any(isinstance(n, ast.Call) and _is_name(n.func, callee) for n in ast.walk(node))
    return None


def _source(relative_path: str) -> str:
    return (_APP / relative_path).read_text(encoding="utf-8")


def test_detector_sees_a_call_and_a_missing_call_and_a_missing_function() -> None:
    source = "async def a(x):\n    await gate(x)\n\nasync def b(x):\n    return x\n\nclass C:\n    def m(self):\n        self.gate(1)\n"
    assert function_calls(source, "a", "gate") is True
    assert function_calls(source, "b", "gate") is False
    assert function_calls(source, "m", "gate") is True
    assert function_calls(source, "missing", "gate") is None


@pytest.mark.architecture
@pytest.mark.parametrize(("relative_path", "function", "gate"), _ENTRIES, ids=[f"{p}::{f}" for p, f, _ in _ENTRIES])
def test_entry_screens_user_text_before_acting_on_it(relative_path: str, function: str, gate: str) -> None:
    called = function_calls(_source(relative_path), function, gate)

    assert called is not None, f"{relative_path} no longer defines {function}; update the table in this test"
    assert called, f"{relative_path}::{function} must call {gate} on the text a user typed (see services/risk/refusal.py)"


@pytest.mark.architecture
@pytest.mark.parametrize(("relative_path", "function"), _WRAPPERS, ids=[f"{p}::{f}" for p, f in _WRAPPERS])
def test_gate_ends_in_the_single_screening_entry(relative_path: str, function: str) -> None:
    assert function_calls(_source(relative_path), function, _SCREEN), (
        f"{relative_path}::{function} must call {_SCREEN}, the only place that detects, records and fails closed"
    )
