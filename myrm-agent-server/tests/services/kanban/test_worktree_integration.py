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

import asyncio
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
    tip = _run_git(
        git_repo, "rev-parse", "--verify", "--quiet", "main-ta"
    ).stdout.strip()
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

    merged, conflicts = await merge_task_worktree(store, task)
    assert merged is True
    assert conflicts == []

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

    merged, conflicts = await merge_task_worktree(store, task)
    assert merged is False
    assert conflicts == ["a.txt"]

    # The failed merge was rolled back: no MERGE_HEAD lingers, so the repo is
    # not stuck in a mid-merge state that would block later merges.
    assert _run_git(git_repo, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0
    assert (
        _run_git(git_repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    )

    # Worktree still exists with the task's commit preserved.
    assert Path(wt).exists()
    assert (
        _run_git(Path(wt), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        == "main-td"
    )


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
    branch = _run_git(
        git_repo, "rev-parse", "--verify", "--quiet", "main-te"
    ).stdout.strip()
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
    assert await merge_task_worktree(store, task) == (True, [])


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

    assert (
        _run_git(git_repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    )
    merged, _ = await merge_task_worktree(store, task)
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


@pytest.mark.asyncio
async def test_merge_auto_commit_failure_preserves_worktree(git_repo: Path) -> None:
    """When the pre-merge auto-commit is rejected, the worktree (and the
    agent's uncommitted edits inside it) must be preserved, not deleted.

    This reproduces a data-loss bug: a blocking pre-commit hook made the
    auto-commit fail, after which the merge path treated the branch as empty
    and cleaned up the worktree, silently dropping the agent's edits.
    """
    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="th", base=str(git_repo), branch="main")

    wt = await create_worktree(str(git_repo), "main", task.task_id)
    assert isinstance(wt, str)
    # Agent edited a file with file tools but never committed it.
    (Path(wt) / "precious.txt").write_text("AGENT_UNCOMMITTED_DATA\n", encoding="utf-8")

    # A pre-commit hook that rejects every commit.
    common_dir = _run_git(
        git_repo, "rev-parse", "--path-format=absolute", "--git-common-dir"
    ).stdout.strip()
    hooks = Path(common_dir) / "hooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    try:
        merged, _ = await merge_task_worktree(store, task)
        assert merged is False
        # Worktree and the uncommitted file survive.
        assert Path(wt).exists()
        assert (
            (Path(wt) / "precious.txt")
            .read_text(encoding="utf-8")
            .startswith("AGENT_UNCOMMITTED_DATA")
        )
    finally:
        hook.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_merge_rejects_unusable_target_branch(git_repo: Path) -> None:
    """A branch name that would be parsed as a git option (leading ``-``)
    must never reach ``git checkout``; the merge is skipped and the worktree
    is preserved instead.
    """
    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="ti", base=str(git_repo), branch="-bad")

    wt = await create_worktree(str(git_repo), "-bad", task.task_id)
    assert isinstance(wt, str)
    (Path(wt) / "u.txt").write_text("data\n", encoding="utf-8")
    _commit_in(Path(wt), "task-i commit")

    merged, _ = await merge_task_worktree(store, task)
    assert merged is False
    # Worktree preserved; base_dir still on main.
    assert Path(wt).exists()
    assert (
        _run_git(git_repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    )


@pytest.mark.asyncio
async def test_cleanup_preserves_dirty_worktree(git_repo: Path) -> None:
    """Safe cleanup keeps a worktree with uncommitted agent edits instead of
    force-deleting it (ARCHIVED/FAILED data-loss protection).

    Only a committed worktree may be removed; a dirty one must survive so the
    user can recover the agent's uncommitted file-tool edits.
    """
    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="tj", base=str(git_repo), branch="main")

    wt = await create_worktree(str(git_repo), "main", task.task_id)
    assert isinstance(wt, str)
    (Path(wt) / "uncommitted.txt").write_text("agent edit\n", encoding="utf-8")

    removed = await cleanup_worktree(store, task)
    assert removed is False
    # Dirty worktree and its uncommitted file survive.
    assert Path(wt).exists()
    assert (Path(wt) / "uncommitted.txt").read_text(encoding="utf-8") == "agent edit\n"

    # After committing, safe cleanup removes the worktree.
    _commit_in(Path(wt), "task-j commit")
    removed = await cleanup_worktree(store, task)
    assert removed is True
    assert not Path(wt).exists()


@pytest.mark.asyncio
async def test_concurrent_merges_serialize_without_failure(git_repo: Path) -> None:
    """Two tasks merging on the same base_dir concurrently must both succeed.

    The per-base_dir merge lock serializes access to git's shared index; the
    pre-fix behavior observed one of two concurrent merges fail with
    "Unable to write index".
    """
    store = InMemoryKanbanStore()
    task_a = await _seed_task(store, task_id="tk", base=str(git_repo), branch="main")
    task_b = await _seed_task(store, task_id="tl", base=str(git_repo), branch="main")

    wt_a = await create_worktree(str(git_repo), "main", task_a.task_id)
    wt_b = await create_worktree(str(git_repo), "main", task_b.task_id)
    assert isinstance(wt_a, str) and isinstance(wt_b, str)

    (Path(wt_a) / "x.txt").write_text("a\n", encoding="utf-8")
    _commit_in(Path(wt_a), "task-k commit")
    (Path(wt_b) / "y.txt").write_text("b\n", encoding="utf-8")
    _commit_in(Path(wt_b), "task-l commit")

    results = await asyncio.gather(
        merge_task_worktree(store, task_a),
        merge_task_worktree(store, task_b),
    )
    assert results == [(True, []), (True, [])]
    # Both commits landed on main (full history: initial + 2 task commits +
    # 2 merge commits; a fixed -N would flake on concurrent merge ordering)
    # and both worktrees were cleaned up.
    log = _run_git(git_repo, "log", "--oneline", "main").stdout
    assert "task-k commit" in log
    assert "task-l commit" in log
    assert not Path(wt_a).exists()
    assert not Path(wt_b).exists()


@pytest.mark.asyncio
async def test_merge_conflict_emits_event_when_store_provided(git_repo: Path) -> None:
    """A failed merge appends a MERGE_CONFLICT event so users see the task's
    code never landed on its branch.

    move_orchestrator passes a store into merge_task_worktree; a conflicting
    merge must surface as an observable task event rather than a silent log.
    """
    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="tm", base=str(git_repo), branch="main")

    wt = await create_worktree(str(git_repo), "main", task.task_id)
    assert isinstance(wt, str)
    (Path(wt) / "a.txt").write_text("task-m conflict\n", encoding="utf-8")
    _commit_in(Path(wt), "task-m conflicting commit")

    (git_repo / "a.txt").write_text("main side\n", encoding="utf-8")
    _commit_in(git_repo, "main-side change")

    from app.services.kanban.move_orchestrator import merge_task_worktree as orchestrate

    merged, _ = await orchestrate(_FakeRunner(store), task, store)
    assert merged is False

    events = await store.list_events(task.task_id)
    kinds = [e.kind.value for e in events]
    assert "merge_conflict" in kinds
    conflict = next(e for e in events if e.kind.value == "merge_conflict")
    assert conflict.payload is not None
    assert "branch" in conflict.payload
    assert conflict.payload["conflicts"] == ["a.txt"]


class _FakeRunner:
    """Minimal TaskRunner exposing merge_task_worktree for orchestration tests."""

    def __init__(self, store: InMemoryKanbanStore) -> None:
        self._store = store

    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        from app.services.kanban.task_runner.worktree import (
            merge_task_worktree as merge,
        )

        return await merge(self._store, task)

    async def cleanup_worktree(self, task: KanbanTask) -> bool:
        return True


@pytest.mark.asyncio
async def test_merge_auto_commit_without_git_identity(tmp_path: Path) -> None:
    """Auto-commit succeeds on repos without a configured git identity.

    Freshly initialized/cloned repos have no user.name/user.email.  The merge
    path auto-commits the agent's file-tool edits; without the identity
    fallback the commit fails ("Please tell me who you are"), the merge is
    skipped, and the task's work silently stays off the branch.
    """
    import os

    from app.core.utils import git_worktree as sw

    repo = tmp_path / "no-identity-repo"
    repo.mkdir()
    _run_git(repo, "init", "-q", "-b", "main")
    _run_git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "initial")
    # No identity configured locally (independent of any global/dev config).
    assert _run_git(repo, "config", "--local", "--get", "user.email").returncode != 0

    # Isolate the fallback from any global identity so the injected author is
    # what actually lands in history.  _GIT_ENV is a shared dict referenced by
    # worktree.py/_worktree_merge.py, so in-place update covers every caller.
    isolated = dict(os.environ)
    isolated.update(
        {
            "HOME": str(tmp_path / "empty-home"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
    )
    original = dict(sw._GIT_ENV)
    sw._GIT_ENV.update(isolated)
    try:
        store = InMemoryKanbanStore()
        task = await _seed_task(store, task_id="tn", base=str(repo), branch="main")

        wt = await create_worktree(str(repo), "main", task.task_id)
        assert isinstance(wt, str)
        # Agent edits via file tools; never commits itself.
        (Path(wt) / "b.txt").write_text("task-n\n", encoding="utf-8")

        merged, conflicts = await merge_task_worktree(store, task)
        assert merged is True
        assert conflicts == []
        author = _run_git(repo, "log", "-1", "--format=%an <%ae>").stdout.strip()
        assert author == "Myrm Agent <agent@myrm.local>"
    finally:
        sw._GIT_ENV.clear()
        sw._GIT_ENV.update(original)


@pytest.mark.asyncio
async def test_git_identity_injects_only_missing_keys(tmp_path: Path) -> None:
    """A repo with ``user.name`` configured keeps it; only the missing
    ``user.email`` is injected, so a real author is never overwritten."""
    import os

    from app.core.utils import git_worktree as sw

    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q", "-b", "main")
    _run_git(repo, "config", "user.name", "Repo Owner")
    _run_git(repo, "config", "commit.gpgsign", "false")

    isolated = dict(os.environ)
    isolated.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
    )
    original = dict(sw._GIT_ENV)
    sw._GIT_ENV.update(isolated)
    try:
        overrides = await sw._git_identity(str(repo))
        assert overrides == ["-c", "user.email=agent@myrm.local"]
    finally:
        sw._GIT_ENV.clear()
        sw._GIT_ENV.update(original)
