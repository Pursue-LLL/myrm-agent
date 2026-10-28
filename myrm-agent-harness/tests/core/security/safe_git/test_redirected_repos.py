"""A repository that sends git to a work tree it does not own is refused, and every honest layout is left alone.

[INPUT]
- core.security.safe_git (POS: hardened argv for the application's automatic git commands)

[OUTPUT]
- Real ``git`` runs: a ``core.worktree`` aimed at an empty directory, another repository, the parent directory, a
  relative path, or a directory whose ``.git`` file names another repository makes the plain ``checkout`` write there
  and the hardened argv refuse to be built, leaving that directory untouched; a path that does not exist is refused
  too. A submodule's checkout, a repository whose work tree is itself, a linked worktree, a separate git directory and a
  subdirectory still get their commands, and only a repository that sets ``core.worktree`` pays a second git process.

[POS]
Enforcement tests for the redirect guard of ``hardened_git_argv``. Every redirect first writes through the plain
command, so a refusal cannot be vacuous.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.core.security.safe_git import GitHardeningError, hardened_git_argv
from tests.support.git_probe import git, plain, run

pytestmark = pytest.mark.skipif(sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX git")


@pytest.fixture(autouse=True)
def _isolated_user_config(isolated_git_config: Path) -> Path:
    return isolated_git_config


def _repository(path: Path, *, keep: str = "f.txt") -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "a@example.com")
    git(path, "config", "user.name", "a")
    (path / keep).write_text("one\n")
    git(path, "add", keep)
    git(path, "commit", "-q", "-m", "init")
    return path


def _empty_directory(base: Path) -> tuple[Path, str]:
    target = base / "target"
    target.mkdir()
    return target, str(target)


def _another_repository(base: Path) -> tuple[Path, str]:
    target = _repository(base / "target", keep="keep.txt")
    return target, str(target)


def _parent_directory(base: Path) -> tuple[Path, str]:
    return base, str(base)


def _directory_with_a_pointer_to_another_repository(base: Path) -> tuple[Path, str]:
    other = _repository(base / "other", keep="keep.txt")
    target = base / "target"
    target.mkdir()
    (target / ".git").write_text(f"gitdir: {other / '.git'}\n")
    return target, str(target)


def _relative_path(base: Path) -> tuple[Path, str]:
    """Relative to the git directory, so ``base/ws/.git/../../target``."""
    target = base / "target"
    target.mkdir()
    return target, "../../target"


_REDIRECTS: dict[str, Callable[[Path], tuple[Path, str]]] = {
    "empty-directory": _empty_directory,
    "another-repository": _another_repository,
    "parent-directory": _parent_directory,
    "pointer-to-another-repository": _directory_with_a_pointer_to_another_repository,
    "relative-path": _relative_path,
}
# ``:/`` names the file from the work tree's root, which is not the directory the command runs in when it is redirected.
_CHECKOUT = ("checkout", "HEAD", "--", ":/f.txt")


def _redirected(tmp_path: Path, name: str, kind: str) -> tuple[Path, Path]:
    """A repository whose ``core.worktree`` names the directory *kind* describes, and that directory."""
    base = tmp_path / name
    workspace = _repository(base / "ws")
    target, value = _REDIRECTS[kind](base)
    git(workspace, "config", "core.worktree", value)
    return workspace, target


def _listing(directory: Path) -> list[str]:
    return sorted(os.listdir(directory))


@pytest.mark.parametrize("kind", list(_REDIRECTS))
def test_a_work_tree_the_repository_does_not_own_is_refused(tmp_path: Path, kind: str) -> None:
    control, control_target = _redirected(tmp_path, "control", kind)
    run(plain(control, *_CHECKOUT), control)
    if not (control_target / "f.txt").exists():
        pytest.skip("this git build does not write into a configured work tree")

    victim, target = _redirected(tmp_path, "victim", kind)
    before = _listing(target)

    with pytest.raises(GitHardeningError):
        hardened_git_argv(_CHECKOUT, repo_dir=victim)

    assert _listing(target) == before


def test_a_work_tree_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    workspace = _repository(tmp_path / "ws")
    git(workspace, "config", "core.worktree", str(tmp_path / "nowhere"))

    with pytest.raises(GitHardeningError):
        hardened_git_argv(("status", "--porcelain"), repo_dir=workspace)


def test_objects_are_still_readable_when_the_work_tree_is_redirected(tmp_path: Path) -> None:
    """Commands that read no work-tree file never reach the redirect, so they skip the listing and stay available."""
    workspace, _ = _redirected(tmp_path, "victim", "another-repository")

    argv = hardened_git_argv(("log", "-1", "--format=%s"), repo_dir=workspace)

    assert run(argv, workspace).stdout.strip() == b"init"


def _own_work_tree(tmp_path: Path) -> Path:
    workspace = _repository(tmp_path / "ws")
    git(workspace, "config", "core.worktree", str(workspace))
    return workspace


def _submodule_checkout(tmp_path: Path) -> Path:
    inner = _repository(tmp_path / "inner")
    outer = _repository(tmp_path / "outer")
    git(outer, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "sub")
    return outer / "sub"


def _linked_worktree(tmp_path: Path) -> Path:
    main = _repository(tmp_path / "main")
    linked = tmp_path / "linked"
    git(main, "worktree", "add", "-q", "--detach", str(linked))
    return linked


def _separate_git_directory(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    git(workspace, "init", "-q", f"--separate-git-dir={tmp_path / 'gitdir'}")
    return workspace


def _subdirectory(tmp_path: Path) -> Path:
    workspace = _repository(tmp_path / "ws")
    (workspace / "pkg").mkdir()
    return workspace / "pkg"


# layout -> (builder, whether the repository's own config sets core.worktree and so is checked)
_HONEST_LAYOUTS: dict[str, tuple[Callable[[Path], Path], bool]] = {
    "work-tree-is-the-repository-itself": (_own_work_tree, True),
    "submodule-checkout": (_submodule_checkout, True),
    "linked-worktree": (_linked_worktree, False),
    "separate-git-directory": (_separate_git_directory, False),
    "subdirectory": (_subdirectory, False),
}


def _worktree_key(directory: Path) -> str:
    probe = run(plain(directory, "config", "--local", "--get", "core.worktree"), directory)
    return probe.stdout.decode().strip()


@pytest.mark.parametrize("layout", list(_HONEST_LAYOUTS))
def test_an_honest_layout_still_gets_its_commands(tmp_path: Path, layout: str) -> None:
    build, sets_worktree_key = _HONEST_LAYOUTS[layout]
    directory = build(tmp_path)
    assert bool(_worktree_key(directory)) is sets_worktree_key

    argv = hardened_git_argv(("status", "--porcelain"), repo_dir=directory)

    assert run(argv, directory).returncode == 0


def test_only_a_repository_that_sets_a_work_tree_pays_for_the_check(tmp_path: Path) -> None:
    ordinary = _repository(tmp_path / "ordinary")
    submodule = _submodule_checkout(tmp_path)

    with patch.object(subprocess, "run", wraps=subprocess.run) as spawned:
        hardened_git_argv(("status", "--porcelain"), repo_dir=ordinary)
        ordinary_cost = spawned.call_count
        hardened_git_argv(("status", "--porcelain"), repo_dir=submodule)
        submodule_cost = spawned.call_count - ordinary_cost

    assert (ordinary_cost, submodule_cost) == (1, 2)
