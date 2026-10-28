"""Fixtures for the tests that drive a real ``git`` (``test_hardening.py``, ``test_hostile_repos.py``).

[INPUT]
- pytest: tmp_path / monkeypatch

[OUTPUT]
- isolated_git_config: no system git config and an empty global file the test may fill in
- markers: directory the marker-writing programs touch
- repo: a repository with one commit and one unstaged edit

[POS]
Keeps the user's real git configuration out of the control and hardened runs alike.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.git_probe import git


@pytest.fixture
def isolated_git_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.delenv("GIT_ALLOW_PROTOCOL", raising=False)
    return global_config


@pytest.fixture
def markers(tmp_path: Path) -> Path:
    directory = tmp_path / "markers"
    directory.mkdir()
    return directory


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    git(workspace, "init", "-q")
    git(workspace, "config", "user.email", "a@example.com")
    git(workspace, "config", "user.name", "a")
    (workspace / "f.txt").write_text("one\n")
    git(workspace, "add", "f.txt")
    git(workspace, "commit", "-q", "-m", "init")
    (workspace / "f.txt").write_text("one\ntwo\n")
    return workspace
