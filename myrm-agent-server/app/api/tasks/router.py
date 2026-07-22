"""Task management API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from myrm_agent_harness.toolkits.tasks import Task, TaskFilters, TaskStatus, TaskStore

from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.tasks.events import task_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


async def get_task_store() -> TaskStore:
    """Get task store instance."""
    from app.lifecycle.task_worker import get_task_store as get_store

    return get_store()


def _parse_task_ids(ids: str | None) -> list[str] | None:
    if ids is None:
        return None
    parsed = [item.strip() for item in ids.split(",") if item.strip()]
    return parsed


def _serialize_task(task: Task, *, include_detail: bool) -> dict[str, object]:
    base: dict[str, object] = {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status.value,
        "priority": task.priority,
        "progress": task.progress,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }
    if not include_detail:
        return base

    base.update(
        {
            "payload": task.payload,
            "result": task.result,
            "error": {
                "error_type": task.error.error_type,
                "message": task.error.message,
                "recoverable": task.error.recoverable.value,
            }
            if task.error
            else None,
            "progress_message": task.progress_message,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
    )
    return base


@router.get("/stream")
async def stream_task_events() -> StreamingResponse:
    """Stream task status updates via SSE."""
    return StreamingResponse(
        task_event_bus.stream_events(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


@router.get("")
async def list_tasks(
    status: str | None = None,
    task_type: str | None = None,
    ids: str | None = None,
    detail: bool = False,
    limit: int = 100,
    offset: int = 0,
    store: TaskStore = Depends(get_task_store),
) -> dict[str, object]:
    """List tasks with filters."""
    task_ids = _parse_task_ids(ids)
    if task_ids == []:
        return {"tasks": [], "total": 0}

    filters = TaskFilters(
        status=TaskStatus(status) if status else None,
        task_type=task_type,
        task_ids=task_ids,
        limit=limit,
        offset=offset,
        order_by="created_at DESC",
    )

    tasks = await store.list_tasks(filters)

    return {
        "tasks": [_serialize_task(t, include_detail=detail) for t in tasks],
        "total": len(tasks),
    }


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    store: TaskStore = Depends(get_task_store),
) -> dict[str, object]:
    """Get task by ID."""
    task = await store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return _serialize_task(task, include_detail=True)


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    store: TaskStore = Depends(get_task_store),
) -> dict[str, object]:
    """Cancel task."""
    task = await store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.is_terminal():
        raise HTTPException(status_code=400, detail="Task already completed")

    if task.cancellation_event:
        task.cancellation_event.set()

    task.mark_cancelled(reason="User cancelled")
    await store.update_task(
        task_id,
        status=TaskStatus.CANCELLED,
        cancellation_reason=task.cancellation_reason,
        completed_at=task.completed_at,
    )

    await task_event_bus.emit(task_id, TaskStatus.CANCELLED)

    return {"message": "Task cancelled", "task_id": task_id}


@router.post("/{task_id}/retry")
async def retry_task(
    task_id: str,
    store: TaskStore = Depends(get_task_store),
) -> dict[str, object]:
    """Retry failed task."""
    task = await store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed tasks can be retried")

    await store.update_task(
        task_id,
        status=TaskStatus.PENDING,
        error=None,
    )

    return {"message": "Task queued for retry", "task_id": task_id}


__all__ = ["router"]
