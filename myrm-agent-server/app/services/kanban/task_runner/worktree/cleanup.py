"""Worktree cleanup and branch deletion helpers for KanbanTaskRunner.

[INPUT]
- myrm_agent_harness.api::KanbanStore (POS: Public protocol re-exports)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask (POS: Kanban domain types)
- worktree.lifecycle (POS: worktree_dir / resolve_base_dir)
- app.core.utils.git_worktree (POS: _remove_worktree / _worktree_is_dirty shared helpers)

[OUTPUT]
- cleanup_worktree (bool: worktree 是否已移除)

[POS]
Worktree 生命周期清理：safe 模式下检测未提交改动并保留 dirty worktree，避免
数据丢失；force 模式（merge 成功后）无条件删除。git 命令基础设施复用
core.utils.git_worktree，避免与 sandbox 两处实现语义漂移。
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.api import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.core.utils.git_worktree import _remove_worktree, _worktree_is_dirty

logger = logging.getLogger(__name__)


async def cleanup_worktree(store: KanbanStore, task: KanbanTask, *, force: bool = False) -> bool:
    """Remove a task's worktree, preserving any uncommitted agent edits.

    ``force=True`` (used after a successful merge) deletes unconditionally —
    the worktree was auto-committed and merged, so nothing is lost.  The
    default safe mode checks for uncommitted changes first and keeps the
    worktree when it is dirty, so an ARCHIVED/FAILED task never silently
    drops file-tool edits the agent never committed.  Returns True when the
    worktree was removed (or absent); False when preserved due to dirtiness.
    """
    from app.services.kanban.task_runner.worktree.lifecycle import (
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

    return await _remove_worktree(base_dir, path, context=f"kanban task {task.task_id[:8]}")
