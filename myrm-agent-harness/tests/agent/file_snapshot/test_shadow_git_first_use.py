"""Tests for the first use of ShadowGitSnapshotStore by several callers at once.

Covers: one ``git init --bare`` for callers that arrive together, and no caller running git
        against a repo that another caller is still configuring.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from myrm_agent_harness.agent.file_snapshot.shadow_git_maintenance import DEFAULT_EXCLUDES
from myrm_agent_harness.agent.file_snapshot.shadow_git_store import ShadowGitSnapshotStore


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


pytestmark = [
    pytest.mark.skipif(not _git_available(), reason="git not found"),
]

_CALLERS = 8
_WAIT_S = 30


@pytest.fixture
def store(tmp_path: Path) -> ShadowGitSnapshotStore:
    return ShadowGitSnapshotStore(store_path=tmp_path / "snapshots")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "hello.py").write_text("print('hello')\n")
    return ws


@pytest.mark.asyncio
async def test_callers_arriving_together_share_one_git_init(
    store: ShadowGitSnapshotStore, workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """Two ``git init --bare`` runs into one directory fail copying the git templates."""
    init_runs = 0
    real_run_cmd = store._run_cmd

    async def run_cmd(*args: str, env: dict[str, str] | None = None, stdin_data: bytes | None = None) -> str:
        nonlocal init_runs
        if args[:3] == ("git", "init", "--bare"):
            init_runs += 1
            await asyncio.sleep(0.05)  # keeps the first initializer in flight while the others arrive
        return await real_run_cmd(*args, env=env, stdin_data=stdin_data)

    monkeypatch.setattr(store, "_run_cmd", run_cmd)

    results = await asyncio.gather(*(store.list_snapshots(str(workspace)) for _ in range(_CALLERS)))

    assert init_runs == 1
    assert results == [[] for _ in range(_CALLERS)]
    assert (store._git_dir / "info" / "exclude").read_text() == DEFAULT_EXCLUDES


@pytest.mark.asyncio
async def test_late_caller_waits_until_the_repo_is_configured(
    store: ShadowGitSnapshotStore, workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """``HEAD`` exists as soon as ``git init`` returns, long before the repo has its config and excludes."""
    head_exists = asyncio.Event()
    release_initializer = asyncio.Event()
    git_ran_before_configured: list[tuple[str, ...]] = []
    real_run_cmd = store._run_cmd
    exclude_file = store._git_dir / "info" / "exclude"

    def configured() -> bool:
        # `git init` writes its own template exclude file, so only our content marks a finished setup.
        return exclude_file.exists() and exclude_file.read_text() == DEFAULT_EXCLUDES

    async def run_cmd(*args: str, env: dict[str, str] | None = None, stdin_data: bytes | None = None) -> str:
        if args[:3] == ("git", "config", "gc.auto"):
            head_exists.set()
            await release_initializer.wait()
        elif args[:2] == ("git", "log") and not configured():
            git_ran_before_configured.append(args)
        return await real_run_cmd(*args, env=env, stdin_data=stdin_data)

    monkeypatch.setattr(store, "_run_cmd", run_cmd)

    async with asyncio.timeout(_WAIT_S):
        first = asyncio.create_task(store.list_snapshots(str(workspace)))
        await head_exists.wait()
        second = asyncio.create_task(store.list_snapshots(str(workspace)))
        await asyncio.sleep(0.05)  # lets the second caller run as far as it can while the first still configures
        release_initializer.set()
        await asyncio.gather(first, second)

    assert git_ran_before_configured == []
