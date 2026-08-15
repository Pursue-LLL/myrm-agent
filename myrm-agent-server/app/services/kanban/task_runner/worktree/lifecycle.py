"""Git worktree lifecycle orchestration for KanbanTaskRunner.

[INPUT]
- myrm_agent_harness.api::KanbanStore (POS: Public protocol re-exports; KanbanStore defined in toolkits.kanban.protocols.)
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)
- app.core.utils.git_worktree (POS: 共享 git worktree 命令基础设施——per-base_dir merge 锁、worktree add/remove/分支删除/merge 组合、auto-commit 与 git identity 兜底、worktree 业务错误类型 WorktreeCreateError/WorktreeErrorReason/_classify_git_error)
- worktree.merge (POS: merge 前置 git 步骤——可合并判断/target 分支切换/分支名校验)
- worktree.cleanup (POS: safe/force 清理)

[OUTPUT]
- resolve_base_dir, resolve_workspace, create_worktree, merge_task_worktree
- worktree_dir, _sanitize_git_branch, _worktree_branch_name (分支名消毒/唯一化，测试直接引用)

[POS]
Git worktree 生命周期编排：resolve workspace path、创建 per-task worktree，
以及把完成的 task worktree merge 回目标分支。git 命令基础设施复用共享层。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from myrm_agent_harness.api import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskEventKind

from app.core.utils.git_worktree import (
    WorktreeCreateError,
    _auto_commit_dirty_worktree,
    _delete_git_branch,
    _get_merge_lock,
    _git_worktree_add,
    _merge_branch_into_current,
)
from app.services.kanban.task_runner.worktree.cleanup import cleanup_worktree
from app.services.kanban.task_runner.worktree.merge import (
    _branch_has_commits,
    _ensure_target_branch_checked_out,
    _is_valid_git_branch,
)

logger = logging.getLogger(__name__)

WORKTREE_DIR_NAME = ".worktrees"


def _sanitize_git_branch(name: str) -> str:
    """Normalize an arbitrary string into a valid git branch name.

    Git forbids spaces, `~ ^ : ? * [ \\`, control chars, leading/trailing
    slashes, `..`, and names starting with `-`.  Replace illegal sequences
    with `-` instead of rejecting them so user-supplied branches degrade
    gracefully instead of failing the whole worktree creation.
    """
    cleaned = name.strip().replace("/", "-").replace("\\", "-")
    cleaned = re.sub(r"[~\^:?*\[\]]", "-", cleaned)
    cleaned = re.sub(r"\.\.+", "-", cleaned)
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    cleaned = cleaned.strip("-")
    return cleaned or "worktree"


def _worktree_branch_name(branch: str, task_id: str) -> str:
    """Unique per-task worktree branch derived from the user-facing branch.

    Two tasks may share the same target ``branch`` (e.g. the repo's current
    branch is the default for every task).  A unique suffix guarantees each
    task's worktree never collides with a sibling task's worktree, so
    ``git worktree add --force -B`` only ever force-updates its own branch
    instead of silently resetting another task's commits.
    """
    return f"{_sanitize_git_branch(branch)}-{task_id[:8]}"


async def resolve_base_dir(store: KanbanStore, task: KanbanTask) -> str | None:
    if task.workspace_path:
        return task.workspace_path
    if not task.board_id:
        return None
    board = await store.get_board(task.board_id)
    if board and board.settings and board.settings.default_workdir:
        return board.settings.default_workdir
    return None


def worktree_dir(base_dir: str, branch: str, task_id: str) -> str:
    safe_name = branch.replace("/", "-").replace("\\", "-")
    return os.path.join(base_dir, WORKTREE_DIR_NAME, f"{safe_name}-{task_id[:8]}")


async def create_worktree(
    base_dir: str, branch: str, task_id: str
) -> str | WorktreeCreateError:
    """Create a per-task worktree. Returns path on success or structured error."""
    worktree_path = worktree_dir(base_dir, branch, task_id)
    unique_branch = _worktree_branch_name(branch, task_id)

    if Path(worktree_path).exists():
        logger.info(
            "Worktree already exists at %s for task %s", worktree_path, task_id[:8]
        )
        return worktree_path

    return await _git_worktree_add(
        base_dir,
        unique_branch,
        worktree_path,
        WORKTREE_DIR_NAME,
        context="kanban task",
    )


async def resolve_workspace(store: KanbanStore, task: KanbanTask) -> str | None:
    base_dir = await resolve_base_dir(store, task)
    if not base_dir:
        return None

    if not task.branch:
        return base_dir

    worktree_path = worktree_dir(base_dir, task.branch, task.task_id)
    created = not Path(worktree_path).exists()
    result = await create_worktree(base_dir, task.branch, task.task_id)
    if isinstance(result, str):
        if created:
            await store.append_event(
                task.task_id,
                TaskEventKind.BRANCH_SWITCHED,
                payload={"branch": task.branch, "worktree_path": result},
            )
        return result

    logger.warning(
        "Worktree creation failed for task %s (reason=%s), falling back to base_dir",
        task.task_id[:8],
        result.reason.value,
    )
    return base_dir


async def merge_task_worktree(store: KanbanStore, task: KanbanTask) -> tuple[bool, list[str]]:
    """Merge a completed task's worktree commits back into its target branch.

    Returns (success, conflict_files).  On success ``conflict_files`` is empty;
    on conflict the worktree and its unique branch are preserved so the
    operator can resolve manually — commits are never silently dropped — and
    the merge is rolled back so later merges on the same repo are not blocked.
    Merges on the same base_dir are serialized to avoid racing on git's shared
    index.
    """
    if not task.branch:
        return True, []

    base_dir = await resolve_base_dir(store, task)
    if not base_dir:
        return True, []

    async with _get_merge_lock(base_dir):
        return await _merge_task_worktree_locked(store, task, base_dir)


async def _merge_task_worktree_locked(
    store: KanbanStore,
    task: KanbanTask,
    base_dir: str,
) -> tuple[bool, list[str]]:
    path = worktree_dir(base_dir, task.branch, task.task_id)
    if not Path(path).exists():
        return True, []

    # Reject unusable branch names before any git command runs; a leading ``-``
    # or git-forbidden characters would otherwise be parsed as CLI options.
    if not _is_valid_git_branch(task.branch):
        logger.warning(
            "Unusable target branch %r for task %s; merge skipped, worktree preserved",
            task.branch,
            task.task_id[:8],
        )
        return False, []

    unique_branch = _worktree_branch_name(task.branch, task.task_id)

    # Auto-commit uncommitted worktree changes so agent edits made with
    # file tools (not git commits) still land in the merge.  If the commit
    # fails the worktree is preserved — cleaning it up would drop those edits.
    if not await _auto_commit_dirty_worktree(
        path, commit_message=f"Auto-commit kanban task {task.task_id[:8]}"
    ):
        logger.warning(
            "Cannot commit dirty worktree %s for task %s; merge skipped, "
            "worktree preserved for manual handling",
            path,
            task.task_id[:8],
        )
        return False, []
    if not await _branch_has_commits(base_dir, unique_branch, task.branch):
        logger.info(
            "No commits on branch %s for task %s; skipping merge",
            unique_branch,
            task.task_id[:8],
        )
        await cleanup_worktree(store, task, force=True)
        await _delete_git_branch(base_dir, unique_branch)
        return True, []

    # Ensure the merge lands on the task's target branch, not whatever is
    # currently checked out.  Default tasks share the current branch so this
    # is usually a no-op, but an explicit target branch must be honored.
    if not await _ensure_target_branch_checked_out(base_dir, task.branch):
        logger.warning(
            "Cannot switch to target branch %s for task %s; merge skipped",
            task.branch,
            task.task_id[:8],
        )
        return False, []

    success, conflicts, stderr = await _merge_branch_into_current(
        base_dir, unique_branch, f"Merge kanban task {task.task_id[:8]}"
    )
    if not success:
        # The worktree and its unique branch are preserved, so no commit is
        # lost; only the failed merge is rolled back by the shared helper.
        logger.warning(
            "Merge of task %s branch %s into %s failed (conflicts=%d): %s",
            task.task_id[:8],
            unique_branch,
            task.branch,
            len(conflicts),
            stderr[:300],
        )
        return False, conflicts
    logger.info(
        "Merged task %s branch %s into %s",
        task.task_id[:8],
        unique_branch,
        task.branch,
    )
    await cleanup_worktree(store, task, force=True)
    await _delete_git_branch(base_dir, unique_branch)
    return True, []
