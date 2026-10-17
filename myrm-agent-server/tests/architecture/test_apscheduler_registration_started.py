"""Architecture: every APScheduler registration must start its scheduler.

APScheduler 4.0 stopped starting a scheduler on entering its async context manager, so an
``async with AsyncScheduler()`` block that only adds schedules silently leaves every job dead: the
process looks healthy and the jobs never run once. This guard fails such a block instead.
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


@pytest.mark.architecture
def test_every_async_scheduler_block_starts_the_scheduler() -> None:
    blocks = _scheduler_blocks()

    assert len(blocks) >= 8, f"expected the known AsyncScheduler registrations, found {len(blocks)}"
    dead = [f"{source.name}:{node.lineno}" for source, node in blocks if not _starts_scheduler(node)]
    assert not dead, "these AsyncScheduler blocks never start the scheduler, so their jobs would never run: " + ", ".join(dead)
