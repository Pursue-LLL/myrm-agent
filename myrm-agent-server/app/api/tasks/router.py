"""Task management API routes.

[INPUT]
- app.lifecycle.task_worker::get_task_store, get_task_worker (POS: TaskStore / TaskWorker provider lifecycle entry)
- app.tasks.events::task_event_bus (POS: SSE task status event hub)

[OUTPUT]
- router: FastAPI tasks router exposing list/detail/stream/retry/cancel APIs

[POS]
HTTP boundary for async task state query and lifecycle actions. It maps TaskStore
state transitions into REST responses plus SSE notifications for frontend task cards.
Cancel and retry are compare-and-set writes, so they never overwrite a concurrent terminal state.
"""

import logging
from datetime import UTC, datetime
from typing import Literal, NoReturn, TypedDict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from myrm_agent_harness.toolkits.tasks import Task, TaskFilters, TaskStatus, TaskStore

from app.api.tasks.deps import get_task_store, get_task_worker
from app.api.tasks.timeline_router import router as timeline_router
from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.tasks.events import task_event_bus
from app.tasks.worker import TaskWorker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])
router.include_router(timeline_router)


type TaskApiRecoverability = Literal["transient", "permanent"]

_CANCELLABLE_STATUSES = (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING)


class TaskApiErrorDetail(TypedDict):
    code: str
    message: str
    recoverable: TaskApiRecoverability


def _raise_task_api_error(
    *,
    status_code: int,
    code: str,
    message: str,
    recoverable: TaskApiRecoverability = "permanent",
) -> NoReturn:
    detail: TaskApiErrorDetail = {
        "code": code,
        "message": message,
        "recoverable": recoverable,
    }
    raise HTTPException(status_code=status_code, detail=detail)


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
        _raise_task_api_error(
            status_code=404,
            code="TASK_NOT_FOUND",
            message="Task not found",
        )

    return _serialize_task(task, include_detail=True)


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    store: TaskStore = Depends(get_task_store),
    worker: TaskWorker | None = Depends(get_task_worker),
) -> dict[str, object]:
    """Cancel an active task and stop its in-flight execution."""
    task = await store.get_task(task_id)
    if not task:
        _raise_task_api_error(
            status_code=404,
            code="TASK_NOT_FOUND",
            message="Task not found",
        )

    cancelled = await store.update_task_if_status(
        task_id,
        _CANCELLABLE_STATUSES,
        status=TaskStatus.CANCELLED,
        cancellation_reason="User cancelled",
        completed_at=datetime.now(UTC),
    )
    if cancelled is None:
        _raise_task_api_error(
            status_code=400,
            code="TASK_ALREADY_COMPLETED",
            message="Only active tasks can be cancelled",
        )

    if worker is not None:
        worker.abort(task_id)
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
        _raise_task_api_error(
            status_code=404,
            code="TASK_NOT_FOUND",
            message="Task not found",
        )

    if task.status != TaskStatus.FAILED:
        _raise_task_api_error(
            status_code=400,
            code="TASK_NOT_RETRYABLE",
            message="Only failed tasks can be retried",
        )

    requeued = await store.update_task_if_status(
        task_id,
        (TaskStatus.FAILED,),
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        progress=0.0,
        progress_message=None,
        started_at=None,
        completed_at=None,
        cancellation_reason=None,
        worker_id=None,
        worker_heartbeat_at=None,
        next_retry_at=None,
    )
    if requeued is None:
        _raise_task_api_error(
            status_code=400,
            code="TASK_NOT_RETRYABLE",
            message="Only failed tasks can be retried",
        )
    await task_event_bus.emit(
        task_id,
        TaskStatus.PENDING,
        {
            "task_type": task.task_type,
            "progress": 0.0,
        },
    )

    return {"message": "Task queued for retry", "task_id": task_id}


from app.api.tasks.test_fixtures import (  # noqa: E402
    router as tasks_test_fixtures_router,
)

router.include_router(tasks_test_fixtures_router)


__all__ = ["router"]
