"""Git worktree isolation helpers for KanbanTaskRunner.

[INPUT]
- myrm_agent_harness.api::KanbanStore (POS: Public protocol re-exports; KanbanStore defined in toolkits.kanban.protocols.)
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)
- app.services.chat.sandbox_worktree (POS: Shared git worktree lifecycle management for chat sandbox sessions.)

[OUTPUT]
- resolve_base_dir, resolve_workspace, cleanup_worktree, merge_task_worktree

[POS]
Git worktree isolation: resolve workspace path, create/cleanup per-task worktrees,
and merge completed task worktrees back into their target branch.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from pathlib import Path

from myrm_agent_harness.api import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskEventKind

from app.services.chat.sandbox_worktree import (
    _GIT_ENV,
    WorktreeCreateError,
    WorktreeErrorReason,
    _classify_git_error,
)
from app.services.kanban.task_runner._worktree_merge import (
    _auto_commit_dirty_worktree,
    _branch_has_commits,
    _ensure_target_branch_checked_out,
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


def _ensure_worktrees_dir_excluded(base_dir: str) -> None:
    """Ensure .worktrees/ is listed in .git/info/exclude."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            return
        common_dir = result.stdout.strip()
        exclude_path = os.path.join(common_dir, "info", "exclude")

        line = f"/{WORKTREE_DIR_NAME}/"
        current = ""
        try:
            current = Path(exclude_path).read_text(encoding="utf-8")
        except OSError:
            pass

        if any(existing_line.strip() == line for existing_line in current.split("\n")):
            return

        prefix = "\n" if current and not current.endswith("\n") else ""
        with open(exclude_path, "a", encoding="utf-8") as f:
            f.write(f"{prefix}{line}\n")
    except Exception:
        pass


async def create_worktree(
    base_dir: str, branch: str, task_id: str
) -> str | WorktreeCreateError:
    """Create a per-task worktree. Returns path on success or structured error."""
    worktree_path = worktree_dir(base_dir, branch, task_id)
    unique_branch = _worktree_branch_name(branch, task_id)

    if Path(worktree_path).exists():
        logger.info("Worktree already exists at %s for task %s", worktree_path, task_id[:8])
        return worktree_path

    try:
        os.makedirs(os.path.dirname(worktree_path), exist_ok=True)
        _ensure_worktrees_dir_excluded(base_dir)

        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "worktree", "add", "--force", "-B", unique_branch, worktree_path, "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=30,
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            reason = _classify_git_error(stderr)
            logger.warning(
                "git worktree add failed (rc=%d, reason=%s): %s",
                result.returncode,
                reason.value,
                stderr[:300],
            )
            return WorktreeCreateError(reason=reason, message=stderr[:300])

        logger.info(
            "Created worktree at %s (branch=%s) for task %s",
            worktree_path,
            unique_branch,
            task_id[:8],
        )
        return worktree_path
    except Exception as exc:
        logger.warning("Failed to create worktree for task %s: %s", task_id[:8], exc)
        return WorktreeCreateError(reason=WorktreeErrorReason.ERROR, message=str(exc)[:300])


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


async def cleanup_worktree(store: KanbanStore, task: KanbanTask) -> None:
    if not task.branch:
        return

    base_dir = await resolve_base_dir(store, task)
    if not base_dir:
        return

    path = worktree_dir(base_dir, task.branch, task.task_id)
    if not Path(path).exists():
        return

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "worktree", "remove", "--force", path],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=30,
            env=_GIT_ENV,
        )
        if result.returncode == 0:
            logger.info("Cleaned up worktree at %s for archived task %s", path, task.task_id[:8])
        else:
            logger.warning(
                "git worktree remove failed (rc=%d): %s",
                result.returncode,
                result.stderr.strip(),
            )
            return
    except Exception as exc:
        logger.warning("Failed to cleanup worktree for task %s: %s", task.task_id[:8], exc)


async def _delete_worktree_branch(base_dir: str, branch: str, task_id: str) -> None:
    """Delete a worktree's unique branch after its commits were merged away.

    Only called once the task's commits have been merged into the target
    branch — deleting the branch earlier would drop commits.
    """
    unique_branch = _worktree_branch_name(branch, task_id)
    try:
        del_result = await asyncio.to_thread(
            subprocess.run,
            ["git", "branch", "-D", unique_branch],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        if del_result.returncode != 0:
            logger.debug(
                "Branch %s for task %s already gone or not deletable: %s",
                unique_branch,
                task_id[:8],
                del_result.stderr.strip(),
            )
    except Exception as exc:
        logger.debug("Branch delete failed for task %s: %s", task_id[:8], exc)


async def merge_task_worktree(store: KanbanStore, task: KanbanTask) -> bool:
    """Merge a completed task's worktree commits back into its target branch.

    Returns True on success (or when there is nothing to merge).  On merge
    conflict the worktree and its unique branch are preserved so the operator
    can resolve manually — commits are never silently dropped.
    """
    if not task.branch:
        return True

    base_dir = await resolve_base_dir(store, task)
    if not base_dir:
        return True

    path = worktree_dir(base_dir, task.branch, task.task_id)
    if not Path(path).exists():
        return True

    unique_branch = _worktree_branch_name(task.branch, task.task_id)

    # Auto-commit uncommitted worktree changes so agent edits made with
    # file tools (not git commits) still land in the merge.
    await _auto_commit_dirty_worktree(path)
    if not await _branch_has_commits(base_dir, unique_branch, task.branch):
        logger.info(
            "No commits on branch %s for task %s; skipping merge",
            unique_branch,
            task.task_id[:8],
        )
        await cleanup_worktree(store, task)
        await _delete_worktree_branch(base_dir, task.branch, task.task_id)
        return True

    # Ensure the merge lands on the task's target branch, not whatever is
    # currently checked out.  Default tasks share the current branch so this
    # is usually a no-op, but an explicit target branch must be honored.
    if not await _ensure_target_branch_checked_out(base_dir, task.branch):
        logger.warning(
            "Cannot switch to target branch %s for task %s; merge skipped",
            task.branch,
            task.task_id[:8],
        )
        return False

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "git",
                "merge",
                "--no-ff",
                unique_branch,
                "-m",
                f"Merge kanban task {task.task_id[:8]}",
            ],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=60,
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            logger.warning(
                "Merge of task %s branch %s into %s failed: %s",
                task.task_id[:8],
                unique_branch,
                task.branch,
                result.stderr.strip()[:300],
            )
            return False
        logger.info(
            "Merged task %s branch %s into %s",
            task.task_id[:8],
            unique_branch,
            task.branch,
        )
        await cleanup_worktree(store, task)
        await _delete_worktree_branch(base_dir, task.branch, task.task_id)
        return True
    except Exception as exc:
        logger.warning(
            "Merge of task %s branch %s failed: %s",
            task.task_id[:8],
            unique_branch,
            exc,
        )
        return False
