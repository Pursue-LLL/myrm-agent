"""Worktree cleanup and branch deletion helpers for KanbanTaskRunner.

[INPUT]
- myrm_agent_harness.api::KanbanStore (POS: Public protocol re-exports)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask (POS: Kanban domain types)
- worktree (POS: worktree_dir / _worktree_branch_name / resolve_base_dir)
- app.services.chat._git_shared (POS: _GIT_ENV / _worktree_is_dirty shared helpers)

[OUTPUT]
- cleanup_worktree (bool: worktree 是否已移除)
- _delete_worktree_branch (None: 合并后删除唯一分支)

[POS]
Worktree 生命周期清理：删除 worktree 目录与唯一分支。与 worktree.py 解耦，
避免主文件超行数预算。脏状态检测复用 _git_shared._worktree_is_dirty，
避免两处实现语义漂移。
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

from myrm_agent_harness.api import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.services.chat._git_shared import _GIT_ENV, _worktree_is_dirty

logger = logging.getLogger(__name__)


async def cleanup_worktree(
    store: KanbanStore, task: KanbanTask, *, force: bool = False
) -> bool:
    """Remove a task's worktree, preserving any uncommitted agent edits.

    ``force=True`` (used after a successful merge) deletes unconditionally —
    the worktree was auto-committed and merged, so nothing is lost.  The
    default safe mode checks for uncommitted changes first and keeps the
    worktree when it is dirty, so an ARCHIVED/FAILED task never silently
    drops file-tool edits the agent never committed.  Returns True when the
    worktree was removed (or absent); False when preserved due to dirtiness.
    """
    from app.services.kanban.task_runner.worktree import (
        resolve_base_dir,
        worktree_dir,
    )

    if not task.branch:
        return True

    base_dir = await resolve_base_dir(store, task)
    if not base_dir:
        return True

    path = worktree_dir(base_dir, task.branch, task.task_id)
    if not Path(path).exists():
        return True

    if not force and await _worktree_is_dirty(path):
        logger.warning(
            "Worktree %s for task %s has uncommitted changes; preserved for "
            "manual handling instead of deleting (would lose data)",
            path,
            task.task_id[:8],
        )
        return False

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
            logger.info(
                "Cleaned up worktree at %s for archived task %s",
                path,
                task.task_id[:8],
            )
            return True
        logger.warning(
            "git worktree remove failed (rc=%d): %s",
            result.returncode,
            result.stderr.strip(),
        )
        return False
    except Exception as exc:
        logger.warning(
            "Failed to cleanup worktree for task %s: %s", task.task_id[:8], exc
        )
        return False


async def _delete_worktree_branch(base_dir: str, branch: str, task_id: str) -> None:
    """Delete a worktree's unique branch after its commits were merged away.

    Only called once the task's commits have been merged into the target
    branch — deleting the branch earlier would drop commits.
    """
    from app.services.kanban.task_runner.worktree import _worktree_branch_name

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
