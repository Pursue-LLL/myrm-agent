"""Media task serialization helper.

[INPUT]
- myrm_agent_harness.toolkits.tasks::Task, TaskStatus (POS: Task model)

[OUTPUT]
- serialize_media_task(task: object) -> dict[str, object]: Serializes queue task for agent status output

[POS]
Server-layer single source of truth for media task serialization.
Used by image_agent_tool, video_agent_tool, and other task-related endpoints.
"""

from __future__ import annotations

# Only status results carry this, so the stable tool schema (and the prompt cache prefix) is untouched. It tells the
# model what to do with a failure instead of leaving it to retry blindly or reword a rejected prompt.
_FAILED_TASK_NEXT_STEP = (
    "If the error is a content-policy or safety rejection, do not reword the prompt to get around it: "
    "tell the user and offer alternatives. "
    "If a parameter was invalid, correct it and call generate again. "
    "Otherwise retry at most once, then report the failure to the user."
)


def serialize_media_task(task: object) -> dict[str, object]:
    """Serialize a queue task for status output in a unified format."""
    from myrm_agent_harness.toolkits.tasks import Task, TaskStatus

    if not isinstance(task, Task):
        return {}

    serialized: dict[str, object] = {
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
    if task.status == TaskStatus.FAILED:
        serialized["next_step"] = _FAILED_TASK_NEXT_STEP
    return serialized
