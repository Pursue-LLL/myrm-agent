"""Git worktree isolation helpers for KanbanTaskRunner.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols (POS: Kanban protocol interfaces.)
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)

[OUTPUT]
- resolve_base_dir, resolve_workspace, cleanup_worktree

[POS]
Git worktree isolation: resolve workspace path, create/cleanup per-task worktrees.
"""

from __future__ import annotations

import asyncio
import logging
import os
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

logger = logging.getLogger(__name__)

WORKTREE_DIR_NAME = ".worktrees"


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

    if Path(worktree_path).exists():
        logger.info("Worktree already exists at %s for task %s", worktree_path, task_id[:8])
        return worktree_path

    try:
        os.makedirs(os.path.dirname(worktree_path), exist_ok=True)
        _ensure_worktrees_dir_excluded(base_dir)

        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "worktree", "add", "--force", "-B", branch, worktree_path, "HEAD"],
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
            branch,
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

    result = await create_worktree(base_dir, task.branch, task.task_id)
    if isinstance(result, str):
        await store.add_event(
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
    except Exception as exc:
        logger.warning("Failed to cleanup worktree for task %s: %s", task.task_id[:8], exc)
