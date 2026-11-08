"""End-to-end tests: an entry the search cannot examine is skipped on either tier, it does not fail the call.

A directory that can be read but not searched (read permission without execute permission) lets its entries be named
and none of them be examined. ripgrep walks on past it, and so must the Python tier: asking the file system about
such an entry with a call that raises would fail the whole Grep or Glob.

Covers:
- A plain folder holding such a directory is searched without it, with or without an ignore file inside it
- A tracked file inside such a directory does not fail the search of a git checkout
- A recorded gitlink whose directory cannot be searched does not fail it either
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.agent.meta_tools.file_search.search_probe import SearchRunner, git, hit_files, listed, write_tree


@pytest.fixture
def unsearchable(restrict_mode: Callable[[Path, int], None]) -> Callable[[Path], None]:
    """Make directories listable but not searchable: their entries can be named, and none of them can be examined."""
    return lambda directory: restrict_mode(directory, 0o644)


def _repository(root: Path, files: dict[str, str], *, committed: bool = False) -> Path:
    write_tree(root, files)
    git(root, "init", "-q")
    git(root, "add", "-A")
    if committed:
        git(root, "commit", "-qm", "initial")
    return root


async def _finds_the_open_file(root: Path, run_glob: SearchRunner, run_grep: SearchRunner) -> None:
    """Both tools answer for the tree: the file next to the locked directory is listed and searched."""
    assert "open.txt" in listed(await run_glob(root, "**/*.txt"))
    assert hit_files(await run_grep(root, "needle"), {"open.txt"}) == {"open.txt"}


class TestPlainFolder:
    async def test_a_directory_that_cannot_be_searched_is_skipped(
        self, plain_dir: Path, unsearchable: Callable[[Path], None], run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"open.txt": "needle\n", "locked/inside.txt": "needle\n"})
        unsearchable(plain_dir / "locked")

        await _finds_the_open_file(plain_dir, run_glob, run_grep)

    async def test_an_ignore_file_inside_it_is_skipped_too(
        self, plain_dir: Path, unsearchable: Callable[[Path], None], run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"open.txt": "needle\n", "locked/.gitignore": "*.log\n", "locked/inside.txt": "needle\n"})
        unsearchable(plain_dir / "locked")

        await _finds_the_open_file(plain_dir, run_glob, run_grep)


@pytest.mark.usefixtures("require_git")
class TestGitCheckout:
    async def test_a_tracked_file_inside_such_a_directory_is_skipped(
        self, tmp_path: Path, unsearchable: Callable[[Path], None], run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        repository = _repository(tmp_path / "repository", {"open.txt": "needle\n", "locked/inside.txt": "needle\n"})
        unsearchable(repository / "locked")

        await _finds_the_open_file(repository, run_glob, run_grep)

    async def test_a_recorded_gitlink_whose_directory_cannot_be_searched_is_skipped(
        self, tmp_path: Path, unsearchable: Callable[[Path], None], run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        repository = _repository(tmp_path / "repository", {"open.txt": "needle\n"})
        dependency = _repository(repository / "libs" / "dep", {"main.py": "needle\n"}, committed=True)
        revision = git(dependency, "rev-parse", "HEAD")
        git(repository, "update-index", "--add", "--cacheinfo", f"160000,{revision},libs/dep")
        unsearchable(dependency)

        await _finds_the_open_file(repository, run_glob, run_grep)
