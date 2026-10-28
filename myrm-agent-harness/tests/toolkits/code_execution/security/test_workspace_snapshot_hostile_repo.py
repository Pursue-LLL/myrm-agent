"""Rolling a workspace back runs no program the repository chose and restores the snapshot's raw bytes.

[INPUT]
- toolkits.code_execution.security.workspace_snapshot (POS: shadow snapshot and one-click rollback)

[OUTPUT]
- Real ``git`` runs: a smudge filter and fsmonitor named by the repository fire on a plain ``read-tree`` and stay silent
  during rollback, which still restores the snapshot's raw bytes even when the filter is required.

[POS]
Enforcement tests for the airbag's restore path: it checks files out, which is where smudge filters run.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.security import workspace_snapshot
from myrm_agent_harness.toolkits.code_execution.security.workspace_snapshot import (
    create_workspace_snapshot,
    rollback_workspace_snapshot,
)
from tests.core.security._git_probe import clear, fired, git, plain, program, run

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX shell scripts and git"
)


@pytest.fixture(autouse=True)
def _isolated_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))


@pytest.fixture
def markers(tmp_path: Path) -> Path:
    directory = tmp_path / "markers"
    directory.mkdir()
    return directory


def _workspace(root: Path) -> tuple[Path, str]:
    """A repository with a snapshot of its dirty state, then the file damaged the way a destructive command would."""
    workspace = root
    workspace.mkdir()
    git(workspace, "init", "-q")
    git(workspace, "config", "user.email", "a@example.com")
    git(workspace, "config", "user.name", "a")
    (workspace / "app.txt").write_text("v1\n")
    git(workspace, "add", "app.txt")
    git(workspace, "commit", "-q", "-m", "init")
    (workspace / "app.txt").write_text("v2 uncommitted\n")
    snapshot = create_workspace_snapshot(workspace)
    assert snapshot.success and snapshot.snapshot_id
    (workspace / "app.txt").write_text("damaged\n")
    return workspace, snapshot.snapshot_id


def _plant(workspace: Path, markers: Path, *, required: bool) -> None:
    (workspace / ".gitattributes").write_text("*.txt filter=evil\n")
    git(workspace, "config", "filter.evil.smudge", program(markers, "smudge", passthrough="cat"))
    git(workspace, "config", "filter.evil.required", "true" if required else "false")
    git(workspace, "status", "--porcelain")  # an index must exist before git consults the monitor
    git(workspace, "config", "core.fsmonitor", program(markers, "fsmonitor"))


def test_a_smudge_filter_and_fsmonitor_stay_silent_while_the_snapshot_is_restored(
    tmp_path: Path, markers: Path
) -> None:
    control, control_id = _workspace(tmp_path / "control")
    _plant(control, markers, required=False)
    run(plain(control, "read-tree", "--reset", "-u", control_id), control)
    if not {"smudge", "fsmonitor"} & fired(markers):
        pytest.skip("this git build runs neither program during read-tree")
    clear(markers)

    victim, snapshot_id = _workspace(tmp_path / "victim")
    _plant(victim, markers, required=False)
    clear(markers)

    assert rollback_workspace_snapshot(victim, snapshot_id) is True
    assert fired(markers) == set()
    assert (victim / "app.txt").read_text() == "v2 uncommitted\n"


def test_a_required_filter_neither_runs_nor_stops_the_rollback(tmp_path: Path, markers: Path) -> None:
    """The snapshot recorded the file's raw bytes, so putting them back unfiltered is the faithful restore."""
    victim, snapshot_id = _workspace(tmp_path / "victim")
    _plant(victim, markers, required=True)
    clear(markers)

    assert rollback_workspace_snapshot(victim, snapshot_id) is True
    assert fired(markers) == set()
    assert (victim / "app.txt").read_text() == "v2 uncommitted\n"


@pytest.mark.parametrize("snapshot_id", ["--help", "HEAD", "abc123", "../../x", ""])
def test_only_a_full_commit_id_ever_reaches_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, snapshot_id: str
) -> None:
    workspace, _ = _workspace(tmp_path / "ws")
    spawned: list[object] = []

    def _record(argv: list[str], *_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        spawned.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(workspace_snapshot, "is_git_repo", lambda _path: True)
    monkeypatch.setattr(subprocess, "run", _record)

    assert rollback_workspace_snapshot(workspace, snapshot_id) is False
    assert spawned == [], "git was spawned for a value that is not a commit id"
