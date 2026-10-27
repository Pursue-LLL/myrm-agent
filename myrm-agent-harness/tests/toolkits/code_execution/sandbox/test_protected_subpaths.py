"""Discovery of the git metadata a sandboxed workspace keeps read-only.

[INPUT]
- code_execution.sandbox.protected_subpaths (POS: Discovery of the git metadata kept read-only in a workspace)

[OUTPUT]
- Which paths are protected for plain repos, child repos, pointer files, links and non-repos.

[POS]
Guards what the providers are asked to enforce; the enforcement itself is tested per provider.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.sandbox import protected_subpaths
from myrm_agent_harness.toolkits.code_execution.sandbox.protected_subpaths import discover_protected_subpaths


def _repo(path: Path, *, hooks: bool = True) -> Path:
    git_dir = path / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text("[core]\n")
    if hooks:
        (git_dir / "hooks").mkdir()
    return git_dir


def _real(*paths: Path) -> tuple[str, ...]:
    return tuple(os.path.join(os.path.realpath(p.parent), p.name) for p in paths)


def test_workspace_repo_config_and_hooks_are_protected(tmp_path: Path) -> None:
    git_dir = _repo(tmp_path)

    assert discover_protected_subpaths(str(tmp_path)) == _real(git_dir / "config", git_dir / "hooks")


def test_only_existing_entries_are_reported(tmp_path: Path) -> None:
    git_dir = _repo(tmp_path, hooks=False)

    assert discover_protected_subpaths(str(tmp_path)) == _real(git_dir / "config")


def test_workspace_without_a_repository_has_nothing_protected(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()

    assert discover_protected_subpaths(str(tmp_path)) == ()


def test_direct_child_repository_is_protected_but_a_grandchild_is_not(tmp_path: Path) -> None:
    child = _repo(tmp_path / "child")
    _repo(tmp_path / "group" / "grandchild")

    assert discover_protected_subpaths(str(tmp_path)) == _real(child / "config", child / "hooks")


def test_pointer_file_protects_itself_and_the_git_dir_inside_the_workspace(tmp_path: Path) -> None:
    git_dir = _repo(tmp_path / "main")
    modules = git_dir / "modules" / "sub"
    modules.mkdir(parents=True)
    (modules / "config").write_text("[core]\n")
    sub_repo = tmp_path / "main" / "sub"
    sub_repo.mkdir()
    (sub_repo / ".git").write_text("gitdir: ../.git/modules/sub\n")

    found = discover_protected_subpaths(str(tmp_path / "main"))

    assert set(_real(sub_repo / ".git", modules / "config", git_dir / "config")) <= set(found)


def test_linked_worktree_protects_the_shared_config_it_names(tmp_path: Path) -> None:
    git_dir = _repo(tmp_path / "main")
    worktree_dir = git_dir / "worktrees" / "wt"
    worktree_dir.mkdir(parents=True)
    (worktree_dir / "commondir").write_text("../..\n")
    linked = tmp_path / "main" / "wt"
    linked.mkdir()
    (linked / ".git").write_text(f"gitdir: {worktree_dir}\n")

    found = discover_protected_subpaths(str(tmp_path / "main"))

    assert _real(git_dir / "config")[0] in found
    assert _real(linked / ".git")[0] in found


def test_pointer_to_a_git_dir_outside_the_workspace_protects_only_the_pointer(tmp_path: Path) -> None:
    outside = _repo(tmp_path / "elsewhere")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".git").write_text(f"gitdir: {outside}\n")

    assert discover_protected_subpaths(str(workspace)) == _real(workspace / ".git")


def test_symlinked_dot_git_protects_the_link_and_its_target(tmp_path: Path) -> None:
    store = _repo(tmp_path / "ws" / "store")
    (tmp_path / "ws" / ".git").symlink_to(store)

    found = discover_protected_subpaths(str(tmp_path / "ws"))

    assert _real(tmp_path / "ws" / ".git")[0] in found
    assert _real(store / "config")[0] in found


def test_unreadable_pointer_target_is_skipped(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("not a pointer\n")

    assert discover_protected_subpaths(str(tmp_path)) == _real(tmp_path / ".git")


def test_child_scan_is_bounded_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(protected_subpaths, "_MAX_CHILD_DIRS", 2)
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()

    with caplog.at_level(logging.WARNING, logger=protected_subpaths.logger.name):
        discover_protected_subpaths(str(tmp_path))

    assert "only the first 2" in caplog.text


def test_missing_workspace_has_nothing_protected(tmp_path: Path) -> None:
    assert discover_protected_subpaths(str(tmp_path / "absent")) == ()
