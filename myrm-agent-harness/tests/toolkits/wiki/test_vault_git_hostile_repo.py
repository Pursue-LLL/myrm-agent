"""A vault snapshot runs no program the vault's repositories name, and skips a vault it cannot make safe or own.

[INPUT]
- toolkits.wiki.portability.vault_git (POS: local git auto-commit of the wiki vault)

[OUTPUT]
- Real ``git`` runs: ``core.fsmonitor``, hooks and clean filters of a ``.git`` that arrived with the vault (ZIP, sync
  folder, restored backup) and ``core.fsmonitor`` of a repository nested below the vault root fire on the plain
  snapshot commands and stay silent during ``commit_vault_git_snapshot``; a conditional include is skipped as
  ``unsafe_repository``. So is a vault whose repository is not its own (``.git`` a file or a symlink, a ``commondir``
  file, a ``core.worktree``, a separate git directory): the plain snapshot commits into another repository, the
  vault's never does. A vault that is a linked worktree of another repository is snapshotted on its own branch.

[POS]
Enforcement tests for the vault commit flow, the one flow that adopts a repository the user may have received as files.
Each vector first fires on the plain commands, so a green run cannot be vacuous.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.portability.vault_git import commit_vault_git_snapshot
from tests.support.git_probe import clear, fired, git, plain, program, run

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX shell scripts and git"
)

_ROOT_PROGRAMS = {"fsmonitor", "hook-post-commit", "hook-reference-transaction"}


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


def _identity(repo: Path) -> None:
    git(repo, "config", "user.email", "a@example.com")
    git(repo, "config", "user.name", "a")


def _delivered_vault(tmp_path: Path, name: str, *, git_dir_as_file: bool = False) -> WikiStructure:
    """A vault whose root already holds a repository, with one commit and a page edited since."""
    structure = WikiStructure(tmp_path / name)
    structure.ensure_structure()
    root = structure.base_dir
    git(root, "init", "-q", *((f"--separate-git-dir={tmp_path / f'{name}-gitdir'}",) if git_dir_as_file else ()))
    _identity(root)
    page = root / "wiki" / "page.md"
    page.write_text("one\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    page.write_text("one\ntwo\n")
    return structure


def _plant_fsmonitor(root: Path, markers: Path) -> None:
    git(root, "config", "core.fsmonitor", program(markers, "fsmonitor"))
    clear(markers)


def _plant_clean_filter(root: Path, markers: Path) -> None:
    (root / ".gitattributes").write_text("*.md filter=evil\n")
    git(root, "config", "filter.evil.clean", program(markers, "filter-clean", passthrough="cat"))
    git(root, "config", "filter.evil.smudge", program(markers, "filter-smudge", passthrough="cat"))
    clear(markers)


def _plant_root_programs(root: Path, markers: Path) -> None:
    _plant_fsmonitor(root, markers)
    for hook in ("post-commit", "reference-transaction"):
        script = root / ".git" / "hooks" / hook
        script.write_text(f"#!/bin/sh\ntouch '{markers}/hook-{hook}'\n")
        script.chmod(0o755)
    clear(markers)


def _vault_with_nested_repository(tmp_path: Path, name: str, markers: Path) -> WikiStructure:
    structure = WikiStructure(tmp_path / name)
    structure.ensure_structure()
    nested = structure.base_dir / "raw" / "evil"
    nested.mkdir(parents=True)
    git(nested, "init", "-q")
    _identity(nested)
    (nested / "f.txt").write_text("one\n")
    git(nested, "add", "f.txt")
    git(nested, "commit", "-q", "-m", "nested")
    git(nested, "config", "core.fsmonitor", program(markers, "fsmonitor"))
    return structure


def _other_repository(tmp_path: Path, name: str) -> Path:
    other = tmp_path / name
    other.mkdir()
    git(other, "init", "-q")
    _identity(other)
    (other / "app.py").write_text("print('hello')\n")
    git(other, "add", "app.py")
    git(other, "commit", "-q", "-m", "someone else's work")
    return other


def _git_directory_symlink(structure: WikiStructure, other: Path) -> Path:
    (structure.base_dir / ".git").symlink_to(other / ".git")
    return other


def _git_directory_file(structure: WikiStructure, other: Path) -> Path:
    (structure.base_dir / ".git").write_text(f"gitdir: {other / '.git'}\n")
    return other


def _common_directory_file(structure: WikiStructure, other: Path) -> Path:
    (structure.base_dir / ".git" / "commondir").write_text(f"{other / '.git'}\n")
    return other


def _work_tree_setting(structure: WikiStructure, other: Path) -> Path:
    git(structure.base_dir, "config", "core.worktree", str(other))
    return structure.base_dir


# kind -> (whether the vault arrives with a repository of its own, how it is aimed at another one; the result is the
# repository whose history a plain snapshot would extend)
_REDIRECTS: dict[str, tuple[bool, Callable[[WikiStructure, Path], Path]]] = {
    "git-directory-is-a-symlink": (False, _git_directory_symlink),
    "git-directory-is-a-file": (False, _git_directory_file),
    "commondir-names-another-repository": (True, _common_directory_file),
    "work-tree-names-another-directory": (True, _work_tree_setting),
}


def _redirected_vault(tmp_path: Path, name: str, kind: str) -> tuple[WikiStructure, Path]:
    """A vault with a page to commit whose repository is not its own, and the repository a plain snapshot extends."""
    other = _other_repository(tmp_path, f"{name}-other")
    has_own_repository, aim = _REDIRECTS[kind]
    if has_own_repository:
        structure = _delivered_vault(tmp_path, name)
    else:
        structure = WikiStructure(tmp_path / name)
        structure.ensure_structure()
        (structure.base_dir / "wiki" / "page.md").write_text("one\n")
    return structure, aim(structure, other)


def _plain_snapshot(root: Path) -> None:
    """The vault's own commands, written the plain way (with no commit yet, git asks for ``status`` instead)."""
    run(plain(root, "add", "-A"), root)
    has_head = run(plain(root, "rev-parse", "--verify", "HEAD"), root).returncode == 0
    check = ("diff-index", "--cached", "--quiet", "HEAD") if has_head else ("status", "--porcelain")
    run(plain(root, *check), root)
    run(plain(root, "commit", "-m", "snapshot", "--no-verify"), root)


def _head(root: Path) -> str:
    return subprocess.run(plain(root, "rev-parse", "HEAD"), capture_output=True, text=True, check=True).stdout.strip()


def test_programs_of_a_repository_delivered_with_the_vault_stay_silent(tmp_path: Path, markers: Path) -> None:
    control = _delivered_vault(tmp_path, "control").base_dir
    _plant_root_programs(control, markers)
    _plain_snapshot(control)
    if not _ROOT_PROGRAMS & fired(markers):
        pytest.skip("this git build runs none of the programs during a snapshot")
    clear(markers)

    victim = _delivered_vault(tmp_path, "victim")
    _plant_root_programs(victim.base_dir, markers)
    before = _head(victim.base_dir)

    result = commit_vault_git_snapshot(victim, reason="session archive")

    assert result.committed is True
    assert result.commit_hash == _head(victim.base_dir)
    assert result.commit_hash != before
    assert fired(markers) == set()


def test_a_clean_filter_named_by_the_delivered_repository_stays_silent(tmp_path: Path, markers: Path) -> None:
    control = _delivered_vault(tmp_path, "control").base_dir
    _plant_clean_filter(control, markers)
    _plain_snapshot(control)
    if "filter-clean" not in fired(markers):
        pytest.skip("this git build does not run a clean filter while staging")
    clear(markers)

    victim = _delivered_vault(tmp_path, "victim")
    _plant_clean_filter(victim.base_dir, markers)

    result = commit_vault_git_snapshot(victim, reason="session archive")

    assert result.committed is True
    assert fired(markers) == set()


def test_a_repository_whose_git_directory_is_a_file_is_skipped_and_runs_nothing(tmp_path: Path, markers: Path) -> None:
    control = _delivered_vault(tmp_path, "control", git_dir_as_file=True).base_dir
    _plant_fsmonitor(control, markers)
    _plain_snapshot(control)
    if "fsmonitor" not in fired(markers):
        pytest.skip("this git build does not run fsmonitor during a snapshot")
    clear(markers)

    victim = _delivered_vault(tmp_path, "victim", git_dir_as_file=True)
    assert (victim.base_dir / ".git").is_file()
    _plant_fsmonitor(victim.base_dir, markers)
    before = _head(victim.base_dir)

    result = commit_vault_git_snapshot(victim, reason="session archive")

    assert result.committed is False
    assert result.skipped_reason == "unsafe_repository"
    assert _head(victim.base_dir) == before
    assert fired(markers) == set()


@pytest.mark.parametrize("kind", list(_REDIRECTS))
def test_a_vault_whose_repository_is_not_its_own_is_skipped_not_committed_to(tmp_path: Path, kind: str) -> None:
    control, extended = _redirected_vault(tmp_path, "control", kind)
    before = _head(extended)
    _plain_snapshot(control.base_dir)
    if _head(extended) == before:
        pytest.skip("this git build does not follow this redirect during a snapshot")

    victim, extended = _redirected_vault(tmp_path, "victim", kind)
    before = _head(extended)

    result = commit_vault_git_snapshot(victim, reason="session archive")

    assert result.committed is False
    assert result.skipped_reason == "unsafe_repository"
    assert _head(extended) == before
    assert not (victim.base_dir / ".gitignore").exists()


def test_a_vault_that_is_a_linked_worktree_is_snapshotted_on_its_own_branch(tmp_path: Path) -> None:
    other = _other_repository(tmp_path, "other")
    structure = WikiStructure(tmp_path / "vault")
    git(other, "worktree", "add", "-q", "-b", "vault-branch", str(structure.base_dir))
    structure.ensure_structure()
    (structure.base_dir / "wiki" / "page.md").write_text("one\n")
    other_before = _head(other)

    result = commit_vault_git_snapshot(structure, reason="session archive")

    assert result.committed is True
    assert result.commit_hash == _head(structure.base_dir)
    assert _head(other) == other_before


def test_a_fsmonitor_of_a_repository_nested_below_the_vault_root_stays_silent(tmp_path: Path, markers: Path) -> None:
    control = _vault_with_nested_repository(tmp_path, "control", markers).base_dir
    git(control, "init", "-q")
    _identity(control)
    (control / "raw" / "evil" / "f.txt").write_text("one\ntwo\n")
    _plain_snapshot(control)
    (control / "raw" / "evil" / "f.txt").write_text("one\ntwo\nthree\n")
    _plain_snapshot(control)
    if "fsmonitor" not in fired(markers):
        pytest.skip("this git build does not consult a nested repository's fsmonitor during a snapshot")
    clear(markers)

    victim = _vault_with_nested_repository(tmp_path, "victim", markers)
    nested_file = victim.base_dir / "raw" / "evil" / "f.txt"
    nested_file.write_text("one\ntwo\n")
    first = commit_vault_git_snapshot(victim, reason="first")
    nested_file.write_text("one\ntwo\nthree\n")
    (victim.base_dir / "wiki" / "page.md").write_text("a page\n")
    second = commit_vault_git_snapshot(victim, reason="second")

    assert first.committed is True
    assert second.committed is True
    assert fired(markers) == set()


def test_a_conditional_include_skips_the_snapshot_instead_of_committing(tmp_path: Path, markers: Path) -> None:
    victim = _delivered_vault(tmp_path, "victim")
    root = victim.base_dir
    _plant_root_programs(root, markers)
    git(root, "config", "includeIf.gitdir:/never/.path", "/dev/null")
    before = _head(root)

    result = commit_vault_git_snapshot(victim, reason="session archive")

    assert result.committed is False
    assert result.skipped_reason == "unsafe_repository"
    assert _head(root) == before
    assert fired(markers) == set()
