"""Git worktree isolation helpers for KanbanTaskRunner."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path

from myrm_agent_harness.toolkits.kanban.protocols import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskEventKind

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


async def create_worktree(base_dir: str, branch: str, task_id: str) -> str | None:
    worktree_path = worktree_dir(base_dir, branch, task_id)

    if Path(worktree_path).exists():
        logger.info("Worktree already exists at %s for task %s", worktree_path, task_id[:8])
        return worktree_path

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "worktree", "add", "--force", "-B", branch, worktree_path, "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                "git worktree add failed (rc=%d): %s",
                result.returncode,
                result.stderr.strip(),
            )
            return None

        logger.info(
            "Created worktree at %s (branch=%s) for task %s",
            worktree_path,
            branch,
            task_id[:8],
        )
        return worktree_path
    except Exception as exc:
        logger.warning("Failed to create worktree for task %s: %s", task_id[:8], exc)
        return None


async def resolve_workspace(store: KanbanStore, task: KanbanTask) -> str | None:
    base_dir = await resolve_base_dir(store, task)
    if not base_dir:
        return None

    if not task.branch:
        return base_dir

    worktree_path = await create_worktree(base_dir, task.branch, task.task_id)
    if worktree_path:
        await store.add_event(
            task.task_id,
            TaskEventKind.BRANCH_SWITCHED,
            payload={"branch": task.branch, "worktree_path": worktree_path},
        )
        return worktree_path

    logger.warning(
        "Worktree creation failed for task %s, falling back to base_dir",
        task.task_id[:8],
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
