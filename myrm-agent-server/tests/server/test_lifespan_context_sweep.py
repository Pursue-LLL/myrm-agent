"""The boot sweeps the chat workspaces for expired spillover files once, and off the event loop.

[INPUT]
- app.server.lifespan::optimized_lifespan / _phase_1b_parallel (POS: the startup functions that start the sweeps)

[OUTPUT]
- Coverage that phase 1b runs no workspace sweep inline and that the maintenance daemon runs the only one

[POS]
Server tests. Phase 1b sweeps nothing inline: on a machine with hundreds of workspaces every pass would hold the
event loop for seconds before the server could answer, so the one boot sweep runs in a thread under the maintenance
daemon. Reads the startup functions' source, like the other lifespan tests.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable

from app.server import lifespan


def _references(function: Callable[..., object], attribute: str) -> list[ast.Attribute]:
    tree = ast.parse(inspect.getsource(function).lstrip())
    return [node for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == attribute]


def test_phase_1b_runs_no_workspace_sweep_inline() -> None:
    assert _references(lifespan._phase_1b_parallel, "sweep_all_workspaces") == []


def test_the_maintenance_daemon_runs_the_only_boot_sweep_in_a_thread() -> None:
    assert len(_references(lifespan.optimized_lifespan, "sweep_all_workspaces")) == 1
    source = inspect.getsource(lifespan.optimized_lifespan)
    assert "asyncio.to_thread(ContextGuardService.sweep_all_workspaces)" in source
    assert "maintenance_daemon.submit(_sweep_spillover_task)" in source
