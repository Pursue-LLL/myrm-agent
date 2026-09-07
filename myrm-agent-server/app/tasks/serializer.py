"""Media task serialization helper.

[INPUT]
- myrm_agent_harness.toolkits.tasks::Task (POS: Task model)

[OUTPUT]
- serialize_media_task(task: object) -> dict[str, object]: Serializes queue task for agent status output

[POS]
Server-layer single source of truth for media task serialization.
Used by image_agent_tool, video_agent_tool, and other task-related endpoints.
"""

from __future__ import annotations

from typing import Any


def serialize_media_task(task: object) -> dict[str, object]:
    """Serialize a queue task for status output in a unified format."""
    from myrm_agent_harness.toolkits.tasks import Task

    if not isinstance(task, Task):
        return {}

    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status.value,
        "result": task.result,
        "error": {
            "error_type": task.error.error_type,
            "message": task.error.message,
            "recoverable": task.error.recoverable.value,
        }
        if task.error
        else None,
        "priority": task.priority,
        "progress": task.progress,
        "progress_message": task.progress_message,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }
