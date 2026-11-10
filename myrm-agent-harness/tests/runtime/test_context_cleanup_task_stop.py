"""ContextCleanupScheduler.stop() ends a running pass instead of leaving its worker thread behind.

The pass walks the workspaces in a thread, which cannot be cancelled and which the interpreter waits for at exit;
a stop therefore signals the pass, and the pass leaves the walk at the next workspace.
"""

import asyncio
import os
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from myrm_agent_harness.runtime.context.cleanup_task import ContextCleanupScheduler


def _expired_context_dirs(sandboxes_root: Path, count: int) -> list[Path]:
    """One user directory holding ``count`` workspaces, each with a context directory older than the retention."""
    user_dir = sandboxes_root / "user_test"
    expired = time.time() - 10 * 86400
    context_dirs = []
    for index in range(count):
        context_dir = user_dir / f"chat_{index}" / ".context" / f"chat_{index}"
        context_dir.mkdir(parents=True)
        os.utime(context_dir, (expired, expired))
        context_dirs.append(context_dir)
    return context_dirs


def test_pass_leaves_the_walk_at_the_next_workspace_once_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context_dirs = _expired_context_dirs(tmp_path, count=5)
    scheduler = ContextCleanupScheduler(tmp_path, max_age_days=7)
    real_rmtree: Callable[[Path], None] = shutil.rmtree

    def stop_during_the_first_removal(path: Path) -> None:
        scheduler._pass_stopped.set()
        real_rmtree(path)

    monkeypatch.setattr(shutil, "rmtree", stop_during_the_first_removal)

    scheduler._cleanup_pass()

    assert sum(1 for context_dir in context_dirs if not context_dir.exists()) == 1


@pytest.mark.asyncio
async def test_stop_signals_a_pass_that_is_still_walking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """stop() returns as soon as the pass has seen the signal, instead of waiting out its timeout and abandoning it."""
    scheduler = ContextCleanupScheduler(tmp_path)
    walking = threading.Event()
    seen_signal: list[bool] = []

    def walk_until_signalled() -> None:
        walking.set()
        seen_signal.append(scheduler._pass_stopped.wait(timeout=10))

    monkeypatch.setattr(scheduler, "_cleanup_pass", walk_until_signalled)
    scheduler.start()
    assert await asyncio.to_thread(walking.wait, 5)

    started = time.monotonic()
    await scheduler.stop(timeout=5.0)

    assert time.monotonic() - started < 2.0
    assert seen_signal == [True]
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_a_stopped_scheduler_cleans_again_after_it_is_started(tmp_path: Path) -> None:
    context_dir = _expired_context_dirs(tmp_path, count=1)[0]
    scheduler = ContextCleanupScheduler(tmp_path, max_age_days=7)
    await scheduler.stop()

    scheduler.start()
    await asyncio.wait_for(_until(lambda: not context_dir.exists()), timeout=5)
    await scheduler.stop()

    assert not context_dir.exists()


async def _until(condition: Callable[[], bool]) -> None:
    while not condition():
        await asyncio.sleep(0.01)
