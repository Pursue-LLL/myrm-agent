"""JSON results the image and video tools share: errors, started tasks and task status.

[INPUT]
- app.lifecycle.task_worker::get_task_store (POS: task queue singleton; imported at call time)
- app.tasks.serializer::serialize_media_task (POS: media task status serializer)

[OUTPUT]
- tool_error(): ``{"error": ...}`` result
- media_task_store(): the task queue store, raising ``RuntimeError`` before the worker has started
- started_tasks_result(): ``{"tasks": [...]}`` answer of a generate call
- media_task_status_result(): result of ``action='status'`` with explicit errors

[POS]
The generate and status halves of ``image_tool`` and ``video_tool`` answer identically, so they are built once here:
a call either returns the tasks it started or an explicit error, never a result that hides a failure.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore

from app.tasks.serializer import serialize_media_task

logger = logging.getLogger(__name__)


def tool_error(message: str, **fields: str) -> str:
    return json.dumps({"error": message, **fields}, ensure_ascii=False)


def media_task_store() -> SQLiteTaskStore:
    """The task queue store.

    Imported at call time: the task worker module imports the executors, and the executors import this package.

    Raises:
        RuntimeError: The task worker has not started, so there is no store yet.
    """
    from app.lifecycle.task_worker import get_task_store

    return get_task_store()


def started_tasks_result(task_type: str, task_ids: Sequence[str], *, message: str) -> str:
    """Answer of a generate call: one entry per task that was queued."""
    tasks = [{"task_id": task_id, "task_type": task_type, "status": "pending"} for task_id in task_ids]
    return json.dumps({"tasks": tasks, "message": message}, ensure_ascii=False)


async def media_task_status_result(task_id: str | None) -> str:
    """State and result of one task, or the explicit reason there is none to report."""
    if not task_id:
        return tool_error("task_id is required when action=status")
    try:
        task = await media_task_store().get_task(task_id)
    except RuntimeError as exc:
        logger.warning("Task store unavailable for media status lookup: %s", exc)
        return tool_error("Task store unavailable", task_id=task_id)
    if task is None:
        return tool_error("Task not found", task_id=task_id)
    return json.dumps(serialize_media_task(task), ensure_ascii=False)
