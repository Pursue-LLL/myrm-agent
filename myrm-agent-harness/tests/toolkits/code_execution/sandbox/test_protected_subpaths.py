"""Discovery of the git metadata a sandboxed workspace keeps read-only.

[INPUT]
- code_execution.sandbox.protected_subpaths (POS: Discovery of the git metadata kept read-only in a workspace)

[OUTPUT]
- Which paths are protected for plain repos, child repos, submodules, pointer files, links and non-repos.

[POS]
Guards what the providers are asked to enforce; the enforcement itself is tested per provider.
"""

from __future__ import annotations

import os
from pathlib import Path

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


def _module(git_dir: Path, name: str, worktree: str | None) -> Path:
    """A submodule git directory the way ``git submodule add`` lays it out below ``git_dir/modules``."""
    module = git_dir / "modules" / name
    (module / "hooks").mkdir(parents=True)
    (module / "HEAD").write_text("ref: refs/heads/main\n")
    setting = "" if worktree is None else f"\tworktree = {worktree}\n"
    (module / "config").write_text(f'[core]\n\tbare = false\n{setting}[remote "origin"]\n\turl = x\n')
    return module


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


def test_nested_submodule_protects_its_git_dir_and_its_working_tree_pointer(tmp_path: Path) -> None:
    git_dir = _repo(tmp_path)
    module = _module(git_dir, "third_party/foo", "../../../../third_party/foo")
    pointer = tmp_path / "third_party" / "foo" / ".git"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("gitdir: ../../.git/modules/third_party/foo\n")

    found = discover_protected_subpaths(str(tmp_path))

    assert set(_real(module / "config", module / "hooks", pointer)) <= set(found)


def test_submodule_of_a_submodule_is_protected_too(tmp_path: Path) -> None:
    git_dir = _repo(tmp_path)
    outer = _module(git_dir, "outer", "../../outer")
    inner = _module(outer, "inner", "../../../../outer/inner")

    found = discover_protected_subpaths(str(tmp_path))

    assert set(_real(outer / "config", inner / "config", inner / "hooks")) <= set(found)


def test_submodule_without_a_working_tree_setting_protects_only_the_git_dir(tmp_path: Path) -> None:
    git_dir = _repo(tmp_path)
    module = _module(git_dir, "sub", None)

    assert discover_protected_subpaths(str(tmp_path)) == _real(
        git_dir / "config", git_dir / "hooks", module / "config", module / "hooks"
    )


def test_submodule_working_tree_outside_the_workspace_is_not_protected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    git_dir = _repo(workspace)
    _module(git_dir, "sub", "../../../../elsewhere")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / ".git").write_text("gitdir: x\n")

    assert _real(tmp_path / "elsewhere" / ".git")[0] not in discover_protected_subpaths(str(workspace))


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


def test_empty_directories_cannot_push_a_repository_out_of_the_examined_children(tmp_path: Path) -> None:
    for index in range(300):
        (tmp_path / f"empty_{index:03d}").mkdir()
    child = _repo(tmp_path / "zzz_repo")

    assert discover_protected_subpaths(str(tmp_path)) == _real(child / "config", child / "hooks")


def test_missing_workspace_has_nothing_protected(tmp_path: Path) -> None:
    assert discover_protected_subpaths(str(tmp_path / "absent")) == ()
