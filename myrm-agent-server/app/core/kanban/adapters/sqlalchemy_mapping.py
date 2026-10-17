"""ORM <-> Domain mapping for kanban models.

Bidirectional conversion between SQLAlchemy ORM models and
framework domain objects (KanbanBoard, KanbanTask).

[INPUT]
myrm_agent_harness.toolkits.kanban.types::BoardSettings/KanbanBoard/KanbanTask (POS: Kanban 域类型)
app.database.models.kanban::KanbanBoardModel/KanbanTaskModel (POS: Kanban domain ORM models)

[OUTPUT]
board_to_domain / board_to_model / apply_board_to_model / task_to_domain /
task_to_model / apply_task_to_model / stored_block_details / status_change_values / get_attachment_ids / set_attachment_ids

[POS]
Kanban ORM Model <-> Domain Entity 双向映射适配层。持久化与域模型的字段级转换枢纽。阻塞的原因、类型与到点时间只对阻塞态任务落库：写整个任务对象的路径用 ``stored_block_details``，只改状态的 UPDATE 用 ``status_change_values``，两者是同一条规则。
"""

from __future__ import annotations

from datetime import datetime

from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskPriority,
    TaskStatus,
)

from app.database.models.kanban import KanbanBoardModel, KanbanTaskModel

# ---------------------------------------------------------------------------
# Board mapping
# ---------------------------------------------------------------------------


def board_to_domain(m: KanbanBoardModel) -> KanbanBoard:
    return KanbanBoard(
        board_id=m.id,
        name=m.name,
        description=m.description,
        settings=BoardSettings(
            max_concurrent_tasks=m.max_concurrent_tasks,
            heartbeat_interval_seconds=m.heartbeat_interval_seconds,
            zombie_timeout_seconds=m.zombie_timeout_seconds,
            max_retries_per_task=m.max_retries_per_task,
            auto_block_after_consecutive_failures=m.auto_block_after_consecutive_failures,
            specify_max_tokens=m.specify_max_tokens,
            auto_specify_on_create=m.auto_specify_on_create,
            default_workdir=m.default_workdir,
            block_recurrence_limit=m.block_recurrence_limit,
        ),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def board_to_model(b: KanbanBoard) -> KanbanBoardModel:
    return KanbanBoardModel(
        id=b.board_id,
        name=b.name,
        description=b.description,
        max_concurrent_tasks=b.settings.max_concurrent_tasks,
        heartbeat_interval_seconds=b.settings.heartbeat_interval_seconds,
        zombie_timeout_seconds=b.settings.zombie_timeout_seconds,
        max_retries_per_task=b.settings.max_retries_per_task,
        auto_block_after_consecutive_failures=b.settings.auto_block_after_consecutive_failures,
        specify_max_tokens=b.settings.specify_max_tokens,
        auto_specify_on_create=b.settings.auto_specify_on_create,
        default_workdir=b.settings.default_workdir,
        block_recurrence_limit=b.settings.block_recurrence_limit,
    )


def apply_board_to_model(b: KanbanBoard, m: KanbanBoardModel) -> None:
    m.name = b.name
    m.description = b.description
    m.max_concurrent_tasks = b.settings.max_concurrent_tasks
    m.heartbeat_interval_seconds = b.settings.heartbeat_interval_seconds
    m.zombie_timeout_seconds = b.settings.zombie_timeout_seconds
    m.max_retries_per_task = b.settings.max_retries_per_task
    m.auto_block_after_consecutive_failures = b.settings.auto_block_after_consecutive_failures
    m.specify_max_tokens = b.settings.specify_max_tokens
    m.auto_specify_on_create = b.settings.auto_specify_on_create
    m.default_workdir = b.settings.default_workdir
    m.block_recurrence_limit = b.settings.block_recurrence_limit


# ---------------------------------------------------------------------------
# Task mapping
# ---------------------------------------------------------------------------


def task_to_domain(m: KanbanTaskModel) -> KanbanTask:
    return KanbanTask(
        task_id=m.id,
        board_id=m.board_id,
        title=m.title,
        description=m.description,
        status=TaskStatus(m.status),
        priority=TaskPriority(m.priority),
        agent_id=m.agent_id,
        model_override=m.model_override,
        parent_task_id=m.parent_task_id,
        workspace_path=m.workspace_path,
        branch=m.branch,
        max_runtime_seconds=m.max_runtime_seconds,
        goal_mode=m.goal_mode,
        goal_max_turns=m.goal_max_turns,
        require_approval=m.require_approval,
        extra_skill_ids=m.extra_skill_ids_json or [],
        retry_count=m.retry_count,
        max_retries=m.max_retries,
        consecutive_failures=m.consecutive_failures,
        block_cycle_count=m.block_cycle_count,
        last_heartbeat_at=m.last_heartbeat_at,
        progress_note=m.progress_note,
        blocked_reason=m.blocked_reason,
        block_kind=BlockKind(m.block_kind) if m.block_kind else None,
        scheduled_until=m.scheduled_until,
        result=m.result,
        error=m.error,
        metadata=m.metadata_json or {},
        created_at=m.created_at,
        updated_at=m.updated_at,
        completed_at=m.completed_at,
    )


def stored_block_details(t: KanbanTask) -> tuple[str | None, str | None, datetime | None]:
    """The reason, kind and wake-up time a row stores for ``t``.

    They describe one block, so a task outside the blocked column stores none of them, whichever code path set its
    status (a move, a cancel, a plan revision).
    """
    if t.status != TaskStatus.BLOCKED:
        return None, None, None
    return t.blocked_reason, t.block_kind.value if t.block_kind else None, t.scheduled_until


def status_change_values(new_status: TaskStatus) -> dict[str, object]:
    """Column values for a status-only UPDATE, which writes no task object and so cannot go through
    ``stored_block_details``: it applies the same rule, clearing the block details unless the task stays blocked.
    """
    values: dict[str, object] = {"status": new_status.value}
    if new_status != TaskStatus.BLOCKED:
        values.update(blocked_reason=None, block_kind=None, scheduled_until=None)
    return values


def task_to_model(t: KanbanTask) -> KanbanTaskModel:
    blocked_reason, block_kind, scheduled_until = stored_block_details(t)
    return KanbanTaskModel(
        id=t.task_id,
        board_id=t.board_id,
        title=t.title,
        description=t.description,
        status=t.status.value,
        priority=t.priority.value,
        agent_id=t.agent_id,
        model_override=t.model_override,
        parent_task_id=t.parent_task_id,
        workspace_path=t.workspace_path,
        branch=t.branch,
        max_runtime_seconds=t.max_runtime_seconds,
        goal_mode=t.goal_mode,
        goal_max_turns=t.goal_max_turns,
        require_approval=t.require_approval,
        retry_count=t.retry_count,
        max_retries=t.max_retries,
        consecutive_failures=t.consecutive_failures,
        block_cycle_count=t.block_cycle_count,
        last_heartbeat_at=t.last_heartbeat_at,
        progress_note=t.progress_note,
        blocked_reason=blocked_reason,
        block_kind=block_kind,
        scheduled_until=scheduled_until,
        result=t.result,
        error=t.error,
        metadata_json=t.metadata if t.metadata else None,
        extra_skill_ids_json=t.extra_skill_ids or None,
        attachment_ids_json=None,
        completed_at=t.completed_at,
    )


def apply_task_to_model(t: KanbanTask, m: KanbanTaskModel) -> None:
    m.title = t.title
    m.description = t.description
    m.status = t.status.value
    m.priority = t.priority.value
    m.agent_id = t.agent_id
    m.model_override = t.model_override
    m.parent_task_id = t.parent_task_id
    m.workspace_path = t.workspace_path
    m.branch = t.branch
    m.max_runtime_seconds = t.max_runtime_seconds
    m.goal_mode = t.goal_mode
    m.goal_max_turns = t.goal_max_turns
    m.require_approval = t.require_approval
    m.retry_count = t.retry_count
    m.max_retries = t.max_retries
    m.consecutive_failures = t.consecutive_failures
    m.block_cycle_count = t.block_cycle_count
    m.last_heartbeat_at = t.last_heartbeat_at
    m.progress_note = t.progress_note
    m.blocked_reason, m.block_kind, m.scheduled_until = stored_block_details(t)
    m.result = t.result
    m.error = t.error
    m.metadata_json = t.metadata if t.metadata else None
    m.extra_skill_ids_json = t.extra_skill_ids or None
    m.completed_at = t.completed_at


def get_attachment_ids(m: KanbanTaskModel) -> list[str]:
    """Extract attachment file IDs from the ORM model."""
    return list(m.attachment_ids_json) if m.attachment_ids_json else []


def set_attachment_ids(m: KanbanTaskModel, ids: list[str]) -> None:
    """Set attachment file IDs on the ORM model."""
    m.attachment_ids_json = ids if ids else None
