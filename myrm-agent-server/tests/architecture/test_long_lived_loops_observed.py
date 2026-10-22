"""Architecture: long-lived background loops must be spawned through the observed entry point.

A loop task held by an instance or module attribute never triggers asyncio's "exception was
never retrieved" report — that report only fires when a task is garbage-collected while its
exception is still unread, and the attribute keeps the task alive. A loop spawned with a bare
``asyncio.create_task`` therefore dies silently: the process keeps looking healthy while the loop
that delivers messages, monitors channels, or notifies users never runs again.

Every process-lifetime loop must be spawned with ``spawn_observed_task`` (``app/core/infra/
background_task.py``), which attaches a done callback that retrieves and logs the exception, and
must pass a ``name=`` so a dead loop is identifiable in dumps.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_SCAN_ROOTS = (
    _SERVER_ROOT / "app" / "channels",
    _SERVER_ROOT / "app" / "core",
)
_OBSERVED_SPAWN = "spawn_observed_task"
# A loop's coroutine contains a top-level `while`; these are the loop bodies we require observed.
_LOOP_MARKERS = ("_loop", "_dispatch_loop", "_health_loop", "_janitor_loop", "_consume_loop")


def _python_sources() -> list[Path]:
    return [path for root in _SCAN_ROOTS for path in root.rglob("*.py") if path.name != "background_task.py"]


def _spawned_coroutine_loops(tree: ast.Module) -> list[ast.Call]:
    """Bare ``asyncio.create_task(...)`` calls whose argument names a loop coroutine."""
    offenders: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "create_task"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        name = arg.func.attr if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) else ""
        if isinstance(arg, ast.Attribute):
            name = arg.attr
        if name in _LOOP_MARKERS:
            offenders.append(node)
    return offenders


@pytest.mark.architecture
def test_long_lived_loops_are_spawned_observed() -> None:
    offenders: list[str] = []
    for source in _python_sources():
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in _spawned_coroutine_loops(tree):
            offenders.append(f"{source.relative_to(_SERVER_ROOT)}:{node.lineno}")

    assert not offenders, (
        "these long-lived loops are spawned with a bare asyncio.create_task, so a crash is silent; "
        "route them through " + _OBSERVED_SPAWN + " with a name=: " + ", ".join(sorted(offenders))
    )


@pytest.mark.architecture
def test_observed_spawn_calls_are_named() -> None:
    unnamed: list[str] = []
    spawns = 0
    for source in _python_sources():
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == _OBSERVED_SPAWN):
                continue
            spawns += 1
            if not any(keyword.arg == "name" for keyword in node.keywords):
                unnamed.append(f"{source.relative_to(_SERVER_ROOT)}:{node.lineno}")

    assert spawns >= 8, f"expected the known observed loops, found {spawns}"
    assert not unnamed, "these spawn_observed_task calls omit the required name= keyword: " + ", ".join(unnamed)
