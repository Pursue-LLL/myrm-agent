"""Kanban worktree isolation subpackage — aggregation facade.

[INPUT]
- app.services.kanban.task_runner.worktree.lifecycle (POS: 生命周期编排——resolve/create/merge)
- app.services.kanban.task_runner.worktree.cleanup (POS: safe/force 清理)
- app.services.kanban.task_runner.worktree.merge (POS: merge 前置 git 步骤)

[OUTPUT]
- resolve_base_dir, resolve_workspace, create_worktree, cleanup_worktree, merge_task_worktree
- worktree_dir, _sanitize_git_branch, _worktree_branch_name (分支名消毒/唯一化，测试直接引用)

[POS]
worktree 域子包聚合出口：lifecycle / cleanup / merge 三模块在此统一 re-export，
供 runner 与包外消费者通过单一入口访问，避免模块级散落。
"""

from app.services.kanban.task_runner.worktree.cleanup import cleanup_worktree
from app.services.kanban.task_runner.worktree.lifecycle import (
    _sanitize_git_branch,
    _worktree_branch_name,
    create_worktree,
    merge_task_worktree,
    resolve_base_dir,
    resolve_workspace,
    worktree_dir,
)

__all__ = [
    "_sanitize_git_branch",
    "_worktree_branch_name",
    "cleanup_worktree",
    "create_worktree",
    "merge_task_worktree",
    "resolve_base_dir",
    "resolve_workspace",
    "worktree_dir",
]
