"""Real-git integration tests for chat sandbox worktree merge and cleanup.

These tests run against a throwaway git repo in ``tmp_path`` to verify the
data-loss guarantees of sandbox session lifecycle:

1. A clean sandbox worktree (agent committed with git) still merges — the
   pre-merge auto-commit must not treat a clean worktree as "cannot commit".
2. A dirty sandbox worktree (agent edited files without committing) is
   auto-committed and merged, so the edits land on the parent branch.
3. Safe cleanup preserves a dirty worktree; force cleanup removes it.

The first two reproduce a merge-blocking bug: ``_auto_commit_dirty_worktree``
returned False for a clean worktree, which made ``merge_sandbox_to_parent``
report "uncommitted changes" and refuse to merge even though there was
nothing to commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services.chat._git_shared import (
    _auto_commit_dirty_worktree,
)
from app.services.chat.sandbox_worktree import (
    cleanup_sandbox_worktree,
    create_sandbox_worktree,
    merge_sandbox_to_parent,
)


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create an initialized git repo with one committed file on 'main'."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q", "-b", "main")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    _run_git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "initial")
    return repo


async def _create_worktree_with_commit(
    base: Path, chat_id: str, filename: str, content: str
) -> Path:
    created = await create_sandbox_worktree(str(base), chat_id)
    assert isinstance(created, str), f"worktree creation failed: {created}"
    wt = Path(created)
    (wt / filename).write_text(content, encoding="utf-8")
    _run_git(wt, "add", ".")
    rc = _run_git(wt, "commit", "-q", "-m", "agent work")
    assert rc.returncode == 0, rc.stderr
    return wt


@pytest.mark.asyncio
async def test_clean_worktree_merges(git_repo: Path) -> None:
    """A clean worktree (agent committed via git) must still merge.

    ``_auto_commit_dirty_worktree`` returns True for a clean worktree, so
    ``merge_sandbox_to_parent`` proceeds instead of reporting uncommitted
    changes and refusing to merge.
    """
    chat_id = "chat-clean-m1"
    wt = await _create_worktree_with_commit(git_repo, chat_id, "work.txt", "clean\n")

    assert await _auto_commit_dirty_worktree(str(wt)) is True

    success, message = await merge_sandbox_to_parent(str(git_repo), chat_id)
    assert success is True, message
    # The agent's commit is reachable from main and the worktree is gone.
    assert _run_git(git_repo, "show", "main:work.txt").stdout == "clean\n"
    assert not wt.exists()


@pytest.mark.asyncio
async def test_dirty_worktree_auto_commit_preserves_edits(git_repo: Path) -> None:
    """Uncommitted file-tool edits are auto-committed and merged, not dropped."""
    chat_id = "chat-dirty-m2"
    created = await create_sandbox_worktree(str(git_repo), chat_id)
    assert isinstance(created, str)
    wt = Path(created)
    (wt / "precious.txt").write_text("AGENT_UNCOMMITTED_EDIT\n", encoding="utf-8")

    success, message = await merge_sandbox_to_parent(str(git_repo), chat_id)
    assert success is True, message
    # The edit survives on main even though the agent never committed it.
    assert (
        _run_git(git_repo, "show", "main:precious.txt").stdout
        == "AGENT_UNCOMMITTED_EDIT\n"
    )
    assert not wt.exists()


@pytest.mark.asyncio
async def test_safe_cleanup_preserves_dirty_worktree(git_repo: Path) -> None:
    """Default cleanup keeps a dirty worktree instead of force-deleting edits."""
    chat_id = "chat-safe-m3"
    created = await create_sandbox_worktree(str(git_repo), chat_id)
    assert isinstance(created, str)
    wt = Path(created)
    (wt / "precious.txt").write_text("KEEP_ME\n", encoding="utf-8")

    removed = await cleanup_sandbox_worktree(str(git_repo), chat_id)
    assert removed is False
    assert wt.exists()
    assert (wt / "precious.txt").read_text(encoding="utf-8") == "KEEP_ME\n"


@pytest.mark.asyncio
async def test_force_cleanup_removes_dirty_worktree(git_repo: Path) -> None:
    """Explicit force cleanup removes the worktree even when dirty."""
    chat_id = "chat-force-m4"
    created = await create_sandbox_worktree(str(git_repo), chat_id)
    assert isinstance(created, str)
    wt = Path(created)
    (wt / "x.txt").write_text("X\n", encoding="utf-8")

    removed = await cleanup_sandbox_worktree(str(git_repo), chat_id, force=True)
    assert removed is True
    assert not wt.exists()
