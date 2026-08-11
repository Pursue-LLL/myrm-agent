"""Batch task fan-out helpers.

[INPUT]
- app.services.kanban::KanbanService (POS: Kanban 业务编排，任务创建委托)
- myrm_agent_harness.toolkits.kanban.types (POS: TaskPriority/TaskStatus)

[OUTPUT]
- fan_out_batch_tasks: 为一组目录扇出同 prompt 的 Kanban 任务

[POS]
任务扇出助手；create_project 与重试/重跑共用，避免重复的 add_task 装配逻辑。
只负责任务创建装配，不承载编排。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.types import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from app.services.kanban import KanbanService

logger = logging.getLogger(__name__)


async def fan_out_batch_tasks(
    kanban: KanbanService,
    *,
    board_id: str,
    project_id: str,
    name: str,
    prompt: str,
    directories: list[str],
    agent_id: str | None,
    model_override: str | None,
    max_runtime_seconds: int | None,
    require_approval: bool,
    artifact_patterns: list[str],
    attempt: int = 0,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Create one Kanban task per directory; return (created_ids, errors).

    Each task points ``workspace_path`` at its target directory and tags
    ``batch_project_id`` plus execution annotations in task metadata.
    ``attempt`` stamps the retry/rerun generation so per-directory aggregation
    can always pick the newest task even when created within the same second.

    Failure semantics belong to the caller: ``create_project`` treats any error
    as fatal (atomic creation, rolls back created tasks); retry/rerun tolerate
    partial failure because a directory that failed to get a fresh task keeps
    its previous task and remains retryable.
    """
    created: list[str] = []
    errors: list[tuple[str, str]] = []
    for index, directory in enumerate(directories):
        title = f"[{name.strip()}] {Path(directory).name or directory}"
        annotations: list[str] = []
        if artifact_patterns:
            annotations.append(
                f"Required output artifacts (glob patterns, relative to "
                f"the workspace root): {', '.join(artifact_patterns)}"
            )
        try:
            task = await kanban.add_task(
                board_id=board_id,
                title=title,
                description=prompt.strip(),
                priority=TaskPriority.NORMAL,
                agent_id=agent_id,
                model_override=model_override,
                max_runtime_seconds=max_runtime_seconds,
                require_approval=require_approval,
                initial_status=TaskStatus.READY,
                workspace_path=directory,
                metadata_patch={
                    "batch_project_id": project_id,
                    "batch_project_name": name.strip(),
                    "batch_directory": directory,
                    "batch_index": index,
                    "batch_attempt": attempt,
                    "artifact_patterns": list(artifact_patterns),
                    "context_annotations": annotations,
                },
            )
            created.append(task.task_id)
        except Exception as exc:  # noqa: BLE001 - 单目录失败不阻断整批
            logger.warning(
                "Batch project %s: failed to create task for %s: %s",
                project_id,
                directory,
                exc,
            )
            errors.append((directory, str(exc)))
    return created, errors
