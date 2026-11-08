"""Tests of the repository boundary a checkout keeps, once per search tier where a search is involved.

git applies the ignore rules of the repository that holds a file and of nothing above its top level. The ripgrep tier
keeps that boundary, and walks a root below a directory that ignores everything below itself (a virtual environment, a
tool cache) as a folder outside any repository.

Covers:
- The ``.gitignore`` of a folder or repository around a checkout never hides its files, nor those of a directory below
  its top level
- A worktree inside its main checkout is not governed by an ignore file only the main checkout holds
- Which directories decide that a root is walked outside a repository: only those between it and the top level of its
  checkout, and only a ``.gitignore`` that ignores everything below itself and negates nothing
- A ``.gitignore`` that cannot be read is no catch-all, and one that is a FIFO is never opened: that would stall the
  flag computation for good
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search.rg_traversal import rg_traversal_args
from tests.agent.meta_tools.file_search.search_probe import (
    PLAIN_FOLDER_FLAGS,
    SearchRunner,
    git,
    hit_files,
    listed,
    write_tree,
)

CHECKOUT_FILES = {"src/app.py": "needle\n", "src/debug.zzz": "needle\n", "build/out.js": "needle\n"}

# A ``.gitignore`` that ignores something but not everything, or takes something back: git reads each as written.
NOT_CATCH_ALL = {
    "extension": b"*.log\n",
    "negation": b"*\n!keep.txt\n",
    "negation_first": b"!keep.txt\n*\n",
    "escaped": b"\\*\n",
    "leading_space": b" *\n",
    "trailing_tab": b"*\t\n",  # git drops trailing spaces only
    "directories_only": b"*/\n",
}


@pytest.fixture(params=["folder", "repository"])
def enclosing(request: pytest.FixtureRequest, tmp_path: Path, require_git: None) -> Path:
    """A directory with ignore rules of its own around the checkout under test: a plain folder or a repository."""
    root = tmp_path / "enclosing"
    write_tree(root, {".gitignore": "*.zzz\nbuild/\n"})
    if request.param == "repository":
        git(root, "init", "-q")
    return root


def _checkout(enclosing: Path) -> Path:
    checkout = enclosing / "checkout"
    write_tree(checkout, CHECKOUT_FILES)
    git(checkout, "init", "-q")
    return checkout


class TestGitignoreAboveTheCheckout:
    async def test_do_not_hide_its_files(self, enclosing: Path, run_glob: SearchRunner, run_grep: SearchRunner) -> None:
        checkout = _checkout(enclosing)

        assert listed(await run_glob(checkout, "**/*")) == set(CHECKOUT_FILES)
        assert hit_files(await run_grep(checkout, "needle"), set(CHECKOUT_FILES)) == set(CHECKOUT_FILES)

    async def test_do_not_hide_the_files_of_a_directory_below_its_top_level(
        self, enclosing: Path, run_glob: SearchRunner
    ) -> None:
        checkout = _checkout(enclosing)

        assert listed(await run_glob(checkout, "**/*", path="src")) == {"app.py", "debug.zzz"}


class TestWorktree:
    async def test_is_not_governed_by_an_ignore_file_that_only_its_main_checkout_holds(
        self, tmp_path: Path, require_git: None, run_glob: SearchRunner
    ) -> None:
        main = tmp_path / "main"
        write_tree(main, {"README.md": "needle\n"})
        git(main, "init", "-q")
        git(main, "add", "README.md")
        git(main, "commit", "-qm", "initial")
        # Uncommitted, so the worktree does not have it: git lists the worktree's ``debug.zzz``.
        write_tree(main, {".gitignore": "*.zzz\n"})
        worktree = main / ".worktrees" / "task"
        git(main, "worktree", "add", "-q", "-b", "task", str(worktree))
        write_tree(worktree, {"src/app.py": "needle\n", "debug.zzz": "needle\n"})

        assert listed(await run_glob(worktree, "**/*")) == {"README.md", "src/app.py", "debug.zzz"}


def _checkout_with_root_below(tmp_path: Path, *directories: str) -> Path:
    """A checkout at ``tmp_path`` and a search root at ``directories`` below it."""
    (tmp_path / ".git").mkdir()
    root = tmp_path.joinpath(*directories)
    root.mkdir(parents=True)
    return root


def _flags_without_stalling(root: Path, fifo: Path) -> list[str]:
    """The flags for ``root``; fails the test instead of hanging it when computing them opens ``fifo``."""
    flags: list[list[str]] = []
    # A daemon thread: opening a FIFO for reading blocks until a writer appears.
    worker = threading.Thread(target=lambda: flags.append(rg_traversal_args(root)), daemon=True)
    worker.start()
    worker.join(timeout=5)
    stalled = worker.is_alive()
    if stalled:
        with contextlib.suppress(OSError):
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))  # lets the blocked read finish
        worker.join(timeout=5)
    assert not stalled, "computing the flags blocked on a .gitignore that is a FIFO"
    return flags[0]


class TestRootBelowADirectoryThatIgnoresEverything:
    @pytest.mark.parametrize("content", NOT_CATCH_ALL.values(), ids=NOT_CATCH_ALL)
    def test_a_gitignore_that_does_not_ignore_everything_keeps_the_boundary(
        self, tmp_path: Path, content: bytes
    ) -> None:
        root = _checkout_with_root_below(tmp_path, ".venv", "lib")
        (tmp_path / ".venv" / ".gitignore").write_bytes(content)

        assert PLAIN_FOLDER_FLAGS.isdisjoint(rg_traversal_args(root))

    def test_an_unreadable_gitignore_keeps_the_boundary(
        self, tmp_path: Path, restrict_mode: Callable[[Path, int], None]
    ) -> None:
        root = _checkout_with_root_below(tmp_path, ".venv", "lib")
        gitignore = tmp_path / ".venv" / ".gitignore"
        gitignore.write_bytes(b"*\n")
        restrict_mode(gitignore, 0o000)

        assert PLAIN_FOLDER_FLAGS.isdisjoint(rg_traversal_args(root))

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs need a POSIX system")
    def test_a_gitignore_that_is_a_fifo_is_never_opened(self, tmp_path: Path) -> None:
        root = _checkout_with_root_below(tmp_path, ".venv", "lib")
        fifo = tmp_path / ".venv" / ".gitignore"
        os.mkfifo(fifo)

        assert PLAIN_FOLDER_FLAGS.isdisjoint(_flags_without_stalling(root, fifo))

    def test_only_the_directories_between_the_root_and_the_top_level_decide(self, tmp_path: Path) -> None:
        top_level = tmp_path / "outer" / "checkout"
        root = top_level / "mid" / "pkg"
        root.mkdir(parents=True)
        (top_level / ".git").mkdir()
        for directory in (root, top_level, top_level.parent, tmp_path):
            (directory / ".gitignore").write_bytes(b"*\n")

        assert PLAIN_FOLDER_FLAGS.isdisjoint(rg_traversal_args(root))

        (top_level / "mid" / ".gitignore").write_bytes(b"*\n")

        assert set(rg_traversal_args(root)) >= PLAIN_FOLDER_FLAGS
