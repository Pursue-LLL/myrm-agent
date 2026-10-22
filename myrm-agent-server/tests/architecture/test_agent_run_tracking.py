"""Architecture test: every server agent run is visible to the hosted idle recycler.

A hosted sandbox is paused once it looks idle, which freezes any agent run still executing inside
it. The liveness endpoint reports a run as in flight only when ``AgentGateway`` counts it or the
caller wraps it in ``track_background_agent_run``. A new ``process_stream`` call site that does
neither is a run the recycler can freeze, so each call site must be listed here with how it is
counted.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[2] / "app"

# Run through ``AgentGateway.execute_stream`` (counted in ``agents.activeCount``).
_GATEWAY_COUNTED = {
    "services/agent/streaming.py": 1,
    "services/agent/wakeup_handler.py": 1,
}
# Call the pipeline directly; the file must wrap the run in ``track_background_agent_run``.
_TRACKED = {
    "core/channel_bridge/agent_executor/executor.py": 1,
    "core/channel_bridge/executor_helpers/approval.py": 1,
    "core/cron/adapters/agent_runner.py": 1,
    "core/eval/executor.py": 1,
    "services/kanban/task_runner/runner.py": 1,
}


def _is_name(node: ast.expr, name: str) -> bool:
    return (isinstance(node, ast.Name) and node.id == name) or (isinstance(node, ast.Attribute) and node.attr == name)


def count_calls(source: str, name: str) -> int:
    """Number of calls to ``name`` (plain or attribute) in ``source``."""
    return sum(1 for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and _is_name(n.func, name))


def opens_run_tracker(source: str) -> bool:
    """Whether ``source`` enters ``track_background_agent_run()`` as a ``with`` item."""
    return any(
        isinstance(item.context_expr, ast.Call) and _is_name(item.context_expr.func, "track_background_agent_run")
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.With)
        for item in node.items
    )


@cache
def _process_stream_sites() -> dict[str, int]:
    sites: dict[str, int] = {}
    for path in _APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "process_stream(" not in text:
            continue
        if calls := count_calls(text, "process_stream"):
            sites[path.relative_to(_APP).as_posix()] = calls
    return sites


def test_detector_counts_attribute_and_plain_calls() -> None:
    assert count_calls("async for e in agent.process_stream(q): pass", "process_stream") == 1
    assert count_calls("s = a.process_stream(q)\nt = b.process_stream(q)", "process_stream") == 2
    assert count_calls("def process_stream(self): ...  # mention process_stream(", "process_stream") == 0


def test_detector_finds_only_a_real_tracker_scope() -> None:
    assert opens_run_tracker("with track_background_agent_run():\n    pass")
    assert opens_run_tracker("with mod.track_background_agent_run(), other():\n    pass")
    assert not opens_run_tracker("track_background_agent_run()")
    assert not opens_run_tracker("with other():\n    pass")


def test_the_scan_sees_the_known_call_sites() -> None:
    assert len(_process_stream_sites()) >= 7, "the source scan found fewer call sites than exist; the guard is blind"


@pytest.mark.architecture
def test_every_process_stream_call_site_is_accounted_for() -> None:
    expected = {**_GATEWAY_COUNTED, **_TRACKED}
    assert _process_stream_sites() == expected, (
        "process_stream call sites changed. A run outside AgentGateway must be wrapped in "
        "track_background_agent_run() so the hosted idle recycler cannot pause the sandbox mid-run; "
        "then register the call site in _TRACKED (or _GATEWAY_COUNTED when it goes through AgentGateway.execute_stream)."
    )


@pytest.mark.architecture
@pytest.mark.parametrize("relative_path", sorted(_GATEWAY_COUNTED))
def test_gateway_counted_site_goes_through_the_gateway(relative_path: str) -> None:
    source = (_APP / relative_path).read_text(encoding="utf-8")

    assert count_calls(source, "execute_stream"), f"{relative_path} no longer routes its run through AgentGateway.execute_stream"


@pytest.mark.architecture
@pytest.mark.parametrize("relative_path", sorted(_TRACKED))
def test_tracked_site_wraps_its_run_in_the_tracker(relative_path: str) -> None:
    source = (_APP / relative_path).read_text(encoding="utf-8")

    assert opens_run_tracker(source), f"{relative_path} runs the agent without track_background_agent_run()"
