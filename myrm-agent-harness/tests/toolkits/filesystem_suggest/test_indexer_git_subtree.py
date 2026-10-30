"""Tests for WorkspacePathIndexer on a real git repository: a workspace subtree lists only its own files.

[INPUT]
- myrm_agent_harness.toolkits.filesystem_suggest.indexer::WorkspacePathIndexer (POS: workspace file lister)

[OUTPUT]
- pytest suite covering a subdirectory workspace, directory names git could read as pathspec magic, sibling directories
  that share the workspace name as a prefix (`plain2`) or match it as a glob (`a1` for `a[1]`), gitignored files and
  nested repositories.

[POS]
myrm-agent-harness/tests/toolkits/filesystem_suggest/test_indexer_git_subtree.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.filesystem_suggest.indexer import WorkspacePathIndexer

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git CLI is required")

_DIRECTORY_NAMES = ["plain", "a[1]", "b*c", "sp ace", "中文目录", "-dash", ":colon", "q?x"]
_SUBTREE_FILES = ["sub/deep.py", "tracked.py", "untracked.txt"]


def _git(top: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(top), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    top = (tmp_path / "repo").resolve()
    top.mkdir()
    _git(top, "init", "-q")
    (top / ".gitignore").write_text("*.log\n", encoding="utf-8")
    for name in [*_DIRECTORY_NAMES, "a1", "plain2"]:
        directory = top / name
        (directory / "sub").mkdir(parents=True)
        (directory / "tracked.py").write_text("x", encoding="utf-8")
        (directory / "sub" / "deep.py").write_text("x", encoding="utf-8")
        (directory / "untracked.txt").write_text("x", encoding="utf-8")
        (directory / "ignored.log").write_text("x", encoding="utf-8")
        _git(top, "add", "--", f":(literal){name}/tracked.py", f":(literal){name}/sub/deep.py")
    (top / "a1" / "only_in_a1.py").write_text("x", encoding="utf-8")
    _git(top, "add", "--", ":(literal)a1/only_in_a1.py")
    return top


def _list(root: Path) -> list[str]:
    WorkspacePathIndexer.clear_cache(root)
    return WorkspacePathIndexer.list_files(root)


@pytest.mark.parametrize("name", _DIRECTORY_NAMES)
def test_a_subdirectory_workspace_lists_exactly_its_own_files(repo: Path, name: str) -> None:
    """Tracked and untracked files appear, gitignored files and sibling directories do not, for any directory name."""
    assert sorted(_list(repo / name)) == _SUBTREE_FILES


def test_the_repository_root_workspace_lists_every_directory(repo: Path) -> None:
    files = _list(repo)

    assert ".gitignore" in files
    assert "a1/only_in_a1.py" in files
    assert "plain/sub/deep.py" in files
    assert not [path for path in files if path.endswith(".log")]


def test_a_nested_directory_inside_a_subdirectory_workspace_is_relative_to_that_workspace(repo: Path) -> None:
    assert _list(repo / "plain" / "sub") == ["deep.py"]


def test_a_nested_repository_is_listed_by_its_bare_name(repo: Path) -> None:
    nested = repo / "plain" / "nested"
    nested.mkdir()
    _git(nested, "init", "-q")
    (nested / "inner.txt").write_text("x", encoding="utf-8")

    assert sorted(_list(repo / "plain")) == ["nested", *_SUBTREE_FILES]
