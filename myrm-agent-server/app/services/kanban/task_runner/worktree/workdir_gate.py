"""Run-entry gate: a task whose working folder the workspace gate would refuse waits for the user.

[INPUT]
- myrm_agent_harness.api::KanbanStore (POS: Public protocol re-exports; KanbanStore defined in toolkits.kanban.protocols.)
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)
- worktree.lifecycle::resolve_base_dir (POS: 任务所在仓库目录)
- app.services.workspace.workspace_path_policy::is_workspace_root_grantable (POS: 已存储的工作区是否仍可交给沙箱)

[OUTPUT]
- WORKDIR_TOO_BROAD_REASON, hold_for_unusable_workdir

[POS]
A task's own ``workspace_path`` and its board's ``default_workdir`` can hold a folder that never met the workspace
path gate (an imported instance, a direct write). A task bound to a folder that is, or contains, a protected
location would hand its agent write access to all of it. ``KanbanTaskRunner.run`` asks this
gate first: it returns a HUMAN block instead of running somewhere else or failing until the retries are spent, and
unblocking the task after the folder was changed is the user's answer. A held task costs no model call.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.api import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import BlockKind, KanbanTask, TaskExecutionResult

from app.services.kanban.task_runner.worktree.lifecycle import resolve_base_dir
from app.services.workspace.workspace_path_policy import is_workspace_root_grantable

logger = logging.getLogger(__name__)

# The frontend translates this exact sentence (shared/config/kanban_blocked_reasons.json, kept equal by
# test_blocked_reason_contract); other consumers show it as written.
WORKDIR_TOO_BROAD_REASON = "The task's working folder is too broad to work in; choose a more specific folder, then continue"


async def hold_for_unusable_workdir(store: KanbanStore, task: KanbanTask) -> TaskExecutionResult | None:
    """Return the block that keeps ``task`` out of its working folder, or None when it may run."""
    base_dir = await resolve_base_dir(store, task)
    if base_dir is None or is_workspace_root_grantable(base_dir):
        return None
    logger.warning("Task %s is held: its working folder %r contains protected locations", task.task_id[:8], base_dir)
    return TaskExecutionResult.blocked(WORKDIR_TOO_BROAD_REASON, block_kind=BlockKind.HUMAN)
