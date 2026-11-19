"""Tests for the harness scratch directories of a workspace: where they sit and that git never sees them."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.utils.scratch_dir import ensure_scratch_dir, scratch_dir


def _git(repository: Path, *args: str) -> str:
    # The caller's own git settings (a global excludes file, config passed in the environment) must not decide what
    # git ignores here.
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_CONFIG")}
    env.update(HOME=str(repository), GIT_CONFIG_NOSYSTEM="1")
    completed = subprocess.run(
        ["git", *args], cwd=repository, env=env, capture_output=True, text=True, timeout=20, check=True
    )
    return completed.stdout


def test_the_directory_sits_under_dot_myrm_of_the_workspace(tmp_path: Path) -> None:
    assert scratch_dir(tmp_path, "exec") == tmp_path / ".myrm" / "exec"
    assert scratch_dir(str(tmp_path), "tee") == tmp_path / ".myrm" / "tee"


def test_ensure_creates_the_directory_and_its_ignore_file(tmp_path: Path) -> None:
    directory = ensure_scratch_dir(tmp_path, "exec")

    assert directory == scratch_dir(tmp_path, "exec")
    assert directory.is_dir()
    assert (directory / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_ensure_can_run_again_and_keeps_an_ignore_file_that_is_there(tmp_path: Path) -> None:
    directory = ensure_scratch_dir(tmp_path, "exec")
    (directory / ".gitignore").write_text("*.keep\n", encoding="utf-8")

    assert ensure_scratch_dir(tmp_path, "exec") == directory
    assert (directory / ".gitignore").read_text(encoding="utf-8") == "*.keep\n"


def test_a_directory_that_cannot_be_created_raises(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "file"
    not_a_directory.write_text("x", encoding="utf-8")

    with pytest.raises(OSError):
        ensure_scratch_dir(not_a_directory, "exec")


def test_an_ignore_file_that_cannot_be_written_does_not_fail_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _refuse(self: Path, *args: object, **kwargs: object) -> int:
        raise PermissionError("read-only file system")

    monkeypatch.setattr(Path, "write_text", _refuse)

    directory = ensure_scratch_dir(tmp_path, "exec")

    assert directory.is_dir()
    assert not (directory / ".gitignore").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_neither_lists_nor_stages_what_lies_in_the_directory(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "mine.txt").write_text("keep\n", encoding="utf-8")
    for name in ("exec", "tee"):
        (ensure_scratch_dir(tmp_path, name) / "harness-file.log").write_text("output\n", encoding="utf-8")

    assert _git(tmp_path, "status", "--porcelain", "-uall").split() == ["??", "mine.txt"]

    _git(tmp_path, "add", "-A")
    assert _git(tmp_path, "ls-files").split() == ["mine.txt"]
