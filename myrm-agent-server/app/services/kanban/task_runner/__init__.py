"""Kanban task runner subpackage — bridges KanbanTask to the agent execution pipeline.

[POS]
TaskRunner 子域。runner 为 TaskRunner 协议实现（聚合出口），profile/stream/worktree
分别为 agent profile 解析、流式累积与附件、Git worktree 隔离。
"""

from app.services.kanban.task_runner.profile import (
    _ResolvedProfile,
    resolve_agent_profile,
)
from app.services.kanban.task_runner.runner import KanbanTaskRunner
from app.services.kanban.task_runner.stream import _classify_content_type
from app.services.kanban.task_runner.worktree import (
    cleanup_worktree,
    resolve_base_dir,
    resolve_workspace,
)

__all__ = [
    "KanbanTaskRunner",
    "_ResolvedProfile",
    "_classify_content_type",
    "cleanup_worktree",
    "resolve_agent_profile",
    "resolve_base_dir",
    "resolve_workspace",
]
