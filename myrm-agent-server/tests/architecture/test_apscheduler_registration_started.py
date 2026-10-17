"""Architecture: every APScheduler registration must start its scheduler, and be observed.

APScheduler 4.0 stopped starting a scheduler on entering its async context manager, so an
``async with AsyncScheduler()`` block that only adds schedules silently leaves every job dead: the
process looks healthy and the jobs never run once. This guard fails such a block instead.

The scheduler task itself must also be spawned through ``spawn_observed_task``: a task whose
exception is never retrieved keeps it silently — the module global that holds it prevents asyncio's
"exception was never retrieved" report from ever firing — so a scheduler that crashes while
initialising would leave the process looking healthy with its jobs permanently dead.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_SCHEDULER_SOURCES = (
    _SERVER_ROOT / "app" / "lifecycle" / "schedulers.py",
    _SERVER_ROOT / "app" / "services" / "memory" / "imports" / "integration_sync_daemon.py",
)
# APScheduler 4.x only processes schedules after one of these calls (`start()` no longer exists).
_START_CALLS = frozenset({"start_in_background", "run_until_stopped"})
# The one spawn entry point that attaches a done callback retrieving the task's exception.
_OBSERVED_SPAWN = "spawn_observed_task"


def _scheduler_blocks() -> list[tuple[Path, ast.AsyncWith]]:
    blocks: list[tuple[Path, ast.AsyncWith]] = []
    for source in _SCHEDULER_SOURCES:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncWith):
                continue
            if any(
                isinstance(item.context_expr, ast.Call) and getattr(item.context_expr.func, "id", "") == "AsyncScheduler"
                for item in node.items
            ):
                blocks.append((source, node))
    return blocks


def _starts_scheduler(block: ast.AsyncWith) -> bool:
    for node in ast.walk(block):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _START_CALLS:
            return True
    return False


def _spawn_calls() -> list[tuple[Path, ast.Call]]:
    calls: list[tuple[Path, ast.Call]] = []
    for source in _SCHEDULER_SOURCES:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == _OBSERVED_SPAWN:
                calls.append((source, node))
    return calls


@pytest.mark.architecture
def test_every_async_scheduler_block_starts_the_scheduler() -> None:
    blocks = _scheduler_blocks()

    assert len(blocks) >= 8, f"expected the known AsyncScheduler registrations, found {len(blocks)}"
    dead = [f"{source.name}:{node.lineno}" for source, node in blocks if not _starts_scheduler(node)]
    assert not dead, "these AsyncScheduler blocks never start the scheduler, so their jobs would never run: " + ", ".join(dead)


@pytest.mark.architecture
def test_every_scheduler_task_is_spawned_with_failure_observation() -> None:
    """A scheduler task started with a bare create_task has its crash silently swallowed."""
    spawns = _spawn_calls()
    blocks = _scheduler_blocks()

    assert len(spawns) >= len(blocks), (
        f"found {len(spawns)} observed spawn(s) for {len(blocks)} AsyncScheduler registration(s); "
        "every scheduler task must go through spawn_observed_task"
    )
    unobserved = [f"{source.name}:{node.lineno}" for source, node in spawns if not _has_name_keyword(node)]
    assert not unobserved, "these spawn_observed_task calls omit the required name= keyword: " + ", ".join(unobserved)


def _has_name_keyword(node: ast.Call) -> bool:
    return any(keyword.arg == "name" for keyword in node.keywords)
