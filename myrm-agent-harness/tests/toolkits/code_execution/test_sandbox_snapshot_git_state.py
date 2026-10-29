"""Enforcement tests for the ``Git:`` line of the sandbox bootstrap snapshot: a working tree whose status could not be read is ``unknown``, never ``clean``.

[INPUT]
- toolkits.code_execution.sandbox_snapshot::generate_sandbox_bootstrap_snapshot / format_bootstrap_snapshot_xml (POS: sandbox bootstrap snapshot generator)
- git (POS: the real binary under test for the repository cases, never mocked)

[OUTPUT]
- Fails when a status that timed out, or a layout the hardened argv refuses, is reported as ``clean``, or when an edited repository is not ``dirty``.

[POS]
The control (a plain repository with an edit is ``dirty``) runs next to the case that must be ``unknown``, and the refused layout first proves with the plain command that
the repository really has an edit, so a green run cannot be vacuous.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution import sandbox_snapshot
from myrm_agent_harness.toolkits.code_execution.sandbox_snapshot import (
    SandboxBootstrapSnapshot,
    format_bootstrap_snapshot_xml,
    generate_sandbox_bootstrap_snapshot,
)
from tests.support.git_probe import git, plain, repository, run


@pytest.mark.parametrize(("dirty", "stated"), [(True, "dirty"), (False, "clean"), (None, "unknown")])
def test_cleanliness_is_stated_only_when_it_was_determined(dirty: bool | None, stated: str) -> None:
    xml = format_bootstrap_snapshot_xml(
        SandboxBootstrapSnapshot(
            working_dir="/w", top_level_entries=(), total_entries_count=0, git_branch="main", git_dirty=dirty
        )
    )

    assert f"(Git: main, {stated})" in xml


def test_a_status_that_timed_out_is_not_reported_as_clean() -> None:
    def _quick_command(cmd: list[str], timeout: float = 1.0, *, merge_stderr: bool = False) -> tuple[int, str]:
        return (0, "main") if "rev-parse" in cmd else (-1, "")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").mkdir()
        with patch(
            "myrm_agent_harness.toolkits.code_execution.sandbox_snapshot._run_quick_command", side_effect=_quick_command
        ):
            snapshot = generate_sandbox_bootstrap_snapshot(root)

    assert snapshot.git_dirty is None
    assert "(Git: main, unknown)" in format_bootstrap_snapshot_xml(snapshot)


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX git")
class TestSnapshotOfARealRepository:
    @pytest.fixture(autouse=True)
    def _isolated_user_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user_config = tmp_path / "user.gitconfig"
        user_config.write_text("")
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(user_config))

    def test_an_edited_repository_is_dirty(self, tmp_path: Path) -> None:
        workspace = repository(tmp_path / "ws")
        (workspace / "f.txt").write_text("one\ntwo\n")

        # The probe's 1.0 s limit is not what this test is about: a loaded runner must not turn dirty into unknown.
        run_probe = sandbox_snapshot._run_quick_command
        with patch.object(
            sandbox_snapshot,
            "_run_quick_command",
            side_effect=lambda cmd, timeout=1.0, **kw: run_probe(cmd, timeout=30.0, **kw),
        ):
            snapshot = generate_sandbox_bootstrap_snapshot(workspace)

        assert snapshot.git_dirty is True
        assert f"(Git: {snapshot.git_branch}, dirty)" in format_bootstrap_snapshot_xml(snapshot)

    def test_a_repository_the_application_will_not_run_git_in_is_unknown_not_clean(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        git(workspace, "init", "-q", f"--separate-git-dir={tmp_path / 'gitdir'}")
        git(workspace, "config", "user.email", "a@example.com")
        git(workspace, "config", "user.name", "a")
        (workspace / "f.txt").write_text("one\n")
        git(workspace, "add", "f.txt")
        git(workspace, "commit", "-q", "-m", "init")
        (workspace / "f.txt").write_text("one\ntwo\n")
        assert run(plain(workspace, "status", "--porcelain"), workspace).stdout.strip(), "the control must see the edit"

        snapshot = generate_sandbox_bootstrap_snapshot(workspace)

        assert snapshot.git_branch is not None
        assert snapshot.git_dirty is None
        assert f"(Git: {snapshot.git_branch}, unknown)" in format_bootstrap_snapshot_xml(snapshot)
