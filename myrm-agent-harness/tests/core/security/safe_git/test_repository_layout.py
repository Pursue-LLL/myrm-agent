"""Enforcement tests for the layout proof of ``hardened_git_argv``: the repository git uses for a folder is the folder's own.

[INPUT]
- git (POS: the real binary under test, never mocked)
- core.security.safe_git::hardened_git_argv / require_own_repository / GitHardeningError

[OUTPUT]
- Fails when a folder whose ``.git`` leads to another repository still gets a command, when a layout the application
  itself uses is refused or costs a git process it should not, or when ``init`` is judged by an ancestor's layout.

[POS]
Every hostile layout first moves another repository's branch through the plain command (the control), so a refusal
cannot be vacuous; every accepted layout runs a real command and counts the git processes spent on the proof.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple
from unittest.mock import patch

import pytest

from myrm_agent_harness.core.security.safe_git import GitHardeningError, hardened_git_argv, require_own_repository
from tests.support.git_probe import git, plain, repository, run

pytestmark = pytest.mark.skipif(sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX git")

_PLANT = ("commit", "--allow-empty", "-q", "-m", "planted")


@pytest.fixture(autouse=True)
def _isolated_user_config(isolated_git_config: Path) -> Path:
    return isolated_git_config


class _Hostile(NamedTuple):
    directory: Path  # the folder that arrived
    observed: Path  # a path whose HEAD shows the damage
    command: tuple[str, ...]


def _tip(path: Path) -> str:
    return run(plain(path, "rev-parse", "HEAD"), path).stdout.decode().strip()


def _victim(base: Path, *, linked: bool = False) -> Path:
    """A repository on ``main`` with two commits, so a ref can be moved back, and optionally a linked worktree."""
    victim = repository(base / "victim", keep="keep.txt")
    git(victim, "branch", "-M", "main")
    (victim / "two.txt").write_text("two\n")
    git(victim, "add", "two.txt")
    git(victim, "commit", "-q", "-m", "two")
    if linked:
        git(victim, "worktree", "add", "-q", "--detach", str(base / "wt"))
    return victim


def _arrived(base: Path) -> Path:
    directory = base / "arrived"
    directory.mkdir(parents=True)
    return directory


def _git_file(base: Path) -> _Hostile:
    victim = _victim(base)
    arrived = _arrived(base)
    (arrived / ".git").write_text(f"gitdir: {victim / '.git'}\n")
    return _Hostile(arrived, victim, _PLANT)


def _git_symlink(base: Path) -> _Hostile:
    victim = _victim(base)
    arrived = _arrived(base)
    (arrived / ".git").symlink_to(victim / ".git")
    return _Hostile(arrived, victim, _PLANT)


def _commondir_file(base: Path) -> _Hostile:
    victim = _victim(base)
    git_dir = _arrived(base) / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    (git_dir / "commondir").write_text(f"{victim / '.git'}\n")
    return _Hostile(git_dir.parent, victim, _PLANT)


def _copied_worktree_folder(base: Path) -> _Hostile:
    """A linked worktree's ``.git`` file copied out: its administrative directory names a different ``.git`` file."""
    victim = _victim(base, linked=True)
    arrived = _arrived(base)
    (arrived / ".git").write_text(f"gitdir: {victim / '.git' / 'worktrees' / 'wt'}\n")
    return _Hostile(arrived, base / "wt", _PLANT)


def _bare_looking_directory(base: Path) -> _Hostile:
    """No ``.git`` at all: the folder itself looks like a git directory whose ``commondir`` is another repository."""
    victim = _victim(base)
    arrived = _arrived(base)
    (arrived / "HEAD").write_text("ref: refs/heads/main\n")
    (arrived / "commondir").write_text(f"{victim / '.git'}\n")
    first = run(plain(victim, "rev-parse", "HEAD~1"), victim).stdout.decode().strip()
    return _Hostile(arrived, victim, ("update-ref", "refs/heads/main", first))


# layout -> whether the file system alone proves it foreign (no git process is spent); a ``.git`` file naming an
# ordinary git directory has the shape of a separate git directory, so git is asked
_HOSTILE: dict[str, tuple[Callable[[Path], _Hostile], bool]] = {
    "git-file-naming-another-repository": (_git_file, False),
    "git-symlink-to-another-repository": (_git_symlink, True),
    "commondir-file-in-the-git-directory": (_commondir_file, True),
    "copied-linked-worktree-folder": (_copied_worktree_folder, True),
    "bare-looking-directory-with-commondir": (_bare_looking_directory, False),
}


@pytest.mark.parametrize("kind", list(_HOSTILE))
def test_a_folder_whose_git_leads_to_another_repository_is_refused(tmp_path: Path, kind: str) -> None:
    build, _ = _HOSTILE[kind]
    control = build(tmp_path / "control")
    before = _tip(control.observed)
    run(plain(control.directory, *control.command), control.directory)
    if _tip(control.observed) == before:
        pytest.skip("this git build does not follow that layout into another repository")

    hostile = build(tmp_path / "victim")

    with pytest.raises(GitHardeningError):
        hardened_git_argv(hostile.command, repo_dir=hostile.directory)


@pytest.mark.parametrize("kind", [name for name, (_, lexical) in _HOSTILE.items() if lexical])
def test_a_foreign_layout_the_file_system_shows_costs_no_git_process(tmp_path: Path, kind: str) -> None:
    hostile = _HOSTILE[kind][0](tmp_path)

    with patch.object(subprocess, "run", wraps=subprocess.run) as spawned, pytest.raises(GitHardeningError):
        hardened_git_argv(hostile.command, repo_dir=hostile.directory)

    assert spawned.call_count == 0


def test_an_environment_that_aims_git_at_another_repository_is_refused(tmp_path: Path) -> None:
    victim = _victim(tmp_path)
    workspace = repository(tmp_path / "ws")
    env = {**os.environ, "GIT_DIR": str(victim / ".git")}
    before = _tip(victim)
    subprocess.run(plain(workspace, *_PLANT), env=env, capture_output=True, check=False)
    if _tip(victim) == before:
        pytest.skip("this git build does not follow GIT_DIR into another repository")

    with pytest.raises(GitHardeningError):
        hardened_git_argv(_PLANT, repo_dir=workspace, env=env)


def test_an_environment_naming_the_repositorys_own_git_directory_is_accepted(tmp_path: Path) -> None:
    workspace = repository(tmp_path / "ws")
    env = {**os.environ, "GIT_DIR": str(workspace / ".git")}

    argv = hardened_git_argv(("status", "--porcelain"), repo_dir=workspace, env=env)

    assert subprocess.run(argv, env=env, capture_output=True, check=False).returncode == 0


def _ordinary(base: Path) -> Path:
    return repository(base / "ws")


def _inside_an_ordinary_repository(base: Path) -> Path:
    inside = repository(base / "ws") / "pkg"
    inside.mkdir()
    return inside


def _linked_worktree(base: Path) -> Path:
    main = repository(base / "main")
    linked = base / "linked"
    git(main, "worktree", "add", "-q", "--detach", str(linked))
    return linked


def _inside_a_linked_worktree(base: Path) -> Path:
    inside = _linked_worktree(base) / "pkg"
    inside.mkdir()
    return inside


def _reached_through_a_symlink(base: Path) -> Path:
    link = base / "link"
    link.symlink_to(repository(base / "ws"))
    return link


def _submodule_checkout(base: Path) -> Path:
    inner = repository(base / "inner")
    outer = repository(base / "outer")
    git(outer, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "sub")
    return outer / "sub"


def _bare_repository(base: Path) -> Path:
    bare = base / "bare.git"
    git(base, "clone", "-q", "--bare", str(repository(base / "src")), str(bare))
    return bare


_STATUS = ("status", "--porcelain")
# layout -> (builder, command, git processes spent before the command: the configuration listing, plus one
# ``rev-parse`` where the file system alone cannot prove the layout)
_OWN_LAYOUTS: dict[str, tuple[Callable[[Path], Path], tuple[str, ...], int]] = {
    "ordinary-repository": (_ordinary, _STATUS, 1),
    "subdirectory-of-an-ordinary-repository": (_inside_an_ordinary_repository, _STATUS, 1),
    "linked-worktree": (_linked_worktree, _STATUS, 1),
    "subdirectory-of-a-linked-worktree": (_inside_a_linked_worktree, _STATUS, 1),
    "reached-through-a-symlink": (_reached_through_a_symlink, _STATUS, 1),
    "submodule-checkout": (_submodule_checkout, _STATUS, 2),
    "bare-repository": (_bare_repository, ("branch", "extra"), 2),
}


@pytest.mark.parametrize("layout", list(_OWN_LAYOUTS))
def test_a_layout_that_is_the_directorys_own_gets_its_commands(tmp_path: Path, layout: str) -> None:
    build, command, expected_spawns = _OWN_LAYOUTS[layout]
    directory = build(tmp_path)

    with patch.object(subprocess, "run", wraps=subprocess.run) as spawned:
        argv = hardened_git_argv(command, repo_dir=directory)

    assert run(argv, directory).returncode == 0
    assert spawned.call_count == expected_spawns


def test_a_separate_git_directory_is_refused_because_git_cannot_tell_it_from_a_planted_pointer(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    git(workspace, "init", "-q", f"--separate-git-dir={tmp_path / 'gitdir'}")
    assert run(plain(workspace, *_STATUS), workspace).returncode == 0

    with pytest.raises(GitHardeningError):
        hardened_git_argv(_STATUS, repo_dir=workspace)


def test_a_directory_that_holds_no_repository_is_left_to_git(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    argv = hardened_git_argv(_STATUS, repo_dir=empty)

    assert run(argv, empty).returncode != 0


def test_init_is_judged_by_the_directory_it_creates_not_by_an_ancestor(tmp_path: Path) -> None:
    hostile = _git_file(tmp_path)
    inner = hostile.directory / "vault"
    inner.mkdir()

    init = run(hardened_git_argv(("init", "-q", "--initial-branch=main"), repo_dir=inner), inner)

    assert init.returncode == 0
    assert (inner / ".git").is_dir()
    assert run(hardened_git_argv(_STATUS, repo_dir=inner), inner).returncode == 0


def test_init_over_an_existing_foreign_git_is_refused(tmp_path: Path) -> None:
    hostile = _git_file(tmp_path)

    with pytest.raises(GitHardeningError):
        hardened_git_argv(("init", "-q"), repo_dir=hostile.directory)


class TestRequireOwnRepository:
    def test_a_foreign_layout_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GitHardeningError):
            require_own_repository(_git_file(tmp_path).directory)

    def test_an_own_repository_and_a_plain_directory_pass(self, tmp_path: Path) -> None:
        plain_directory = tmp_path / "plain"
        plain_directory.mkdir()

        require_own_repository(repository(tmp_path / "ws"))
        require_own_repository(plain_directory)
