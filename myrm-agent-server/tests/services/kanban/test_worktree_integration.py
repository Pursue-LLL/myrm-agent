"""Real-git integration tests for kanban worktree isolation and merging.

These tests run against a throwaway git repo in ``tmp_path`` to verify the
two reliability guarantees the unit tests cannot cover:

1. Two tasks sharing the same target branch never collide — each gets a
   unique per-task worktree branch, so ``git worktree add -B`` cannot reset
   a sibling task's commits.
2. A completed task's commits are merged back into its target branch and
   its worktree/branch are cleaned up afterwards.

The bugs these cover (branch-reset data loss and lost isolation) are only
reproducible with real git; mocked subprocess tests cannot catch them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask

from app.services.kanban.task_runner.worktree import (
    _sanitize_git_branch,
    _worktree_branch_name,
    cleanup_worktree,
    create_worktree,
    merge_task_worktree,
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


def _commit_in(repo: Path, message: str) -> str:
    _run_git(repo, "add", "-A")
    result = _run_git(repo, "commit", "-q", "-m", message)
    assert result.returncode == 0, result.stderr
    return _run_git(repo, "rev-parse", "HEAD").stdout.strip()


async def _seed_task(
    store: InMemoryKanbanStore,
    *,
    task_id: str,
    base: str,
    branch: str,
) -> KanbanTask:
    await store.save_board(KanbanBoard(board_id="b1", name="Board"))
    task = KanbanTask(
        task_id=task_id,
        board_id="b1",
        title=f"Task {task_id}",
        workspace_path=base,
        branch=branch,
    )
    return await store.save_task(task)


@pytest.mark.asyncio
async def test_sanitize_git_branch_removes_illegal_chars() -> None:
    assert _sanitize_git_branch("feat/space x") == "feat-space-x"
    assert _sanitize_git_branch("..double..dot..") == "double-dot"
    assert _sanitize_git_branch("bad~^:?*[name") == "bad-name"
    assert _sanitize_git_branch("") == "worktree"
    assert _sanitize_git_branch("-leading") == "leading"


@pytest.mark.asyncio
async def test_worktree_branch_is_unique_per_task() -> None:
    assert _worktree_branch_name("main", "taskAAAA") == "main-taskAAAA"
    assert _worktree_branch_name("main", "taskBBBB") == "main-taskBBBB"
    assert _worktree_branch_name("feat/x", "taskAAAA") == "feat-x-taskAAAA"


@pytest.mark.asyncio
async def test_parallel_tasks_share_branch_without_collision(
    git_repo: Path,
) -> None:
    """Two tasks using the same target branch each get an isolated worktree."""
    store = InMemoryKanbanStore()
    task_a = await _seed_task(store, task_id="ta", base=str(git_repo), branch="main")
    task_b = await _seed_task(store, task_id="tb", base=str(git_repo), branch="main")

    wt_a = await create_worktree(str(git_repo), "main", task_a.task_id)
    wt_b = await create_worktree(str(git_repo), "main", task_b.task_id)

    assert isinstance(wt_a, str)
    assert isinstance(wt_b, str)
    assert wt_a != wt_b

    # Each worktree checks out its own unique branch.
    branch_a = _run_git(Path(wt_a), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    branch_b = _run_git(Path(wt_b), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert branch_a == "main-ta"
    assert branch_b == "main-tb"


@pytest.mark.asyncio
async def test_serial_tasks_do_not_lose_commits(git_repo: Path) -> None:
    """A later task using the same branch must not reset an earlier task's commits.

    This reproduces the pre-fix data loss: ``git worktree add -B main`` after a
    sibling task committed on ``main`` silently resets the branch to HEAD.
    """
    store = InMemoryKanbanStore()
    task_a = await _seed_task(store, task_id="ta", base=str(git_repo), branch="main")
    task_b = await _seed_task(store, task_id="tb", base=str(git_repo), branch="main")

    wt_a = await create_worktree(str(git_repo), "main", task_a.task_id)
    assert isinstance(wt_a, str)
    # Task A makes a commit in its worktree.
    (Path(wt_a) / "a.txt").write_text("task-a change\n", encoding="utf-8")
    commit_a = _commit_in(Path(wt_a), "task-a commit")

    # Task B cleans up after A and creates its own worktree on the same branch.
    await cleanup_worktree(store, task_a)
    wt_b = await create_worktree(str(git_repo), "main", task_b.task_id)
    assert isinstance(wt_b, str)

    # Task A's commit must still exist on its unique branch (branch preserved).
    tip = _run_git(git_repo, "rev-parse", "--verify", "--quiet", "main-ta").stdout.strip()
    assert tip == commit_a


@pytest.mark.asyncio
async def test_merge_task_worktree_lands_commits_on_target(
    git_repo: Path,
) -> None:
    """A completed task's worktree commits are merged into the target branch."""
    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="tc", base=str(git_repo), branch="main")

    wt = await create_worktree(str(git_repo), "main", task.task_id)
    assert isinstance(wt, str)
    (Path(wt) / "b.txt").write_text("task-c\n", encoding="utf-8")
    _commit_in(Path(wt), "task-c commit")

    merged = await merge_task_worktree(store, task)
    assert merged is True

    # The commit is now reachable from the target branch's history.
    log = _run_git(git_repo, "log", "--oneline", "-3", "main").stdout
    assert "task-c commit" in log

    # Worktree directory and unique branch are removed.
    assert not Path(wt).exists()
    branches = _run_git(git_repo, "branch", "--list", "main-tc").stdout
    assert "main-tc" not in branches


@pytest.mark.asyncio
async def test_merge_conflict_preserves_worktree(git_repo: Path) -> None:
    """On merge conflict the worktree and commits are preserved for manual fix."""
    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="td", base=str(git_repo), branch="main")

    wt = await create_worktree(str(git_repo), "main", task.task_id)
    assert isinstance(wt, str)
    (Path(wt) / "a.txt").write_text("conflicting change\n", encoding="utf-8")
    _commit_in(Path(wt), "task-d conflicting commit")

    # Advance the target branch in a conflicting way first.
    (git_repo / "a.txt").write_text("main side change\n", encoding="utf-8")
    _commit_in(git_repo, "main-side change")

    merged = await merge_task_worktree(store, task)
    assert merged is False

    # Worktree still exists with the task's commit preserved.
    assert Path(wt).exists()
    assert _run_git(Path(wt), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main-td"


@pytest.mark.asyncio
async def test_cleanup_removes_worktree_keeps_branch(git_repo: Path) -> None:
    """cleanup_worktree removes the worktree dir but preserves the branch.

    The unique branch keeps the task's commits so an ARCHIVED or FAILED task
    never loses history; the branch is only deleted after a successful merge.
    """
    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="te", base=str(git_repo), branch="main")

    wt = await create_worktree(str(git_repo), "main", task.task_id)
    assert isinstance(wt, str)
    (Path(wt) / "c.txt").write_text("x\n", encoding="utf-8")
    _commit_in(Path(wt), "task-e commit")

    await cleanup_worktree(store, task)

    assert not Path(wt).exists()
    # Branch still present with the commit.
    branch = _run_git(git_repo, "rev-parse", "--verify", "--quiet", "main-te").stdout.strip()
    assert branch != ""


@pytest.mark.asyncio
async def test_merge_idempotent_when_no_worktree(git_repo: Path) -> None:
    """merge_task_worktree is a no-op when the worktree was already removed."""
    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="tf", base=str(git_repo), branch="main")

    wt = await create_worktree(str(git_repo), "main", task.task_id)
    assert isinstance(wt, str)
    (Path(wt) / "d.txt").write_text("y\n", encoding="utf-8")
    _commit_in(Path(wt), "task-f commit")

    await cleanup_worktree(store, task)
    assert await merge_task_worktree(store, task) is True


@pytest.mark.asyncio
async def test_merge_lands_on_explicit_target_branch(git_repo: Path) -> None:
    """An explicit task branch is honored even when it differs from the
    currently checked-out branch.

    The merge must land on ``feature-x`` (created from HEAD on first use),
    not on whatever branch happens to be checked out in base_dir.
    """
    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="tg", base=str(git_repo), branch="feature-x")

    wt = await create_worktree(str(git_repo), "feature-x", task.task_id)
    assert isinstance(wt, str)
    (Path(wt) / "feat.txt").write_text("task-g\n", encoding="utf-8")
    task_commit = _commit_in(Path(wt), "task-g feature commit")

    assert _run_git(git_repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    merged = await merge_task_worktree(store, task)
    assert merged is True

    # base_dir switched to feature-x to perform the merge.
    assert (
        _run_git(git_repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        == "feature-x"
    )

    # The merge's second parent is the task commit, so feature-x history
    # contains it, and main is untouched.
    second_parent = _run_git(git_repo, "rev-parse", "feature-x^2").stdout.strip()
    assert second_parent == task_commit
    main_log = _run_git(git_repo, "log", "--oneline", "-2", "main").stdout
    assert "task-g feature commit" not in main_log

    # Worktree and unique branch are cleaned up after the merge.
    assert not Path(wt).exists()
    branches = _run_git(git_repo, "branch", "--list", "feature-x-tg").stdout
    assert "feature-x-tg" not in branches
