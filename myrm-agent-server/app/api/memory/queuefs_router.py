"""[POS]: app/api/memory/queuefs_router.py
[INPUT]: HTTP requests for async QueueFS DAG task execution and hierarchical semantic locks.
[OUTPUT]: FastAPI APIRouter exposing endpoints under /queuefs prefix.
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.queuefs import (
    AcquireLockRequest,
    AcquireLockResponse,
    CheckLockResponse,
    QueueFSStatsResponse,
    QueueFSTaskResponse,
    QueueFSTaskSubmitRequest,
    ReleaseLockRequest,
    ReleaseLockResponse,
    SemanticTaskStatusAPI,
)
from app.services.memory.queuefs_service import (
    LockAcquisitionConflictError,
    QueueFSService,
    TaskNotFoundError,
    get_queuefs_service,
)

router = APIRouter(prefix="/queuefs", tags=["memory-queuefs"])


@router.post(
    "/tasks/submit",
    response_model=QueueFSTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit resource to asynchronous QueueFS DAG pipeline",
)
async def submit_queuefs_task(request: QueueFSTaskSubmitRequest) -> QueueFSTaskResponse:
    """Submit a context or resource processing task to run asynchronously."""
    service: QueueFSService = get_queuefs_service()
    return service.submit_task(request)


@router.get(
    "/tasks/{task_id}",
    response_model=QueueFSTaskResponse,
    summary="Get QueueFS DAG task status and progress",
)
async def get_queuefs_task(task_id: str) -> QueueFSTaskResponse:
    """Query current status and progress of an asynchronous task."""
    service: QueueFSService = get_queuefs_service()
    task = service.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    return task


@router.post(
    "/tasks/{task_id}/execute",
    response_model=QueueFSTaskResponse,
    summary="Execute entire QueueFS DAG pipeline under path lock",
)
async def execute_queuefs_pipeline(task_id: str) -> QueueFSTaskResponse:
    """Execute all DAG stages sequentially protected by resource path lock."""
    service: QueueFSService = get_queuefs_service()
    try:
        return await service.execute_pipeline(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/tasks/{task_id}/advance",
    response_model=QueueFSTaskResponse,
    summary="Advance QueueFS task to next DAG stage",
)
async def advance_queuefs_stage(task_id: str) -> QueueFSTaskResponse:
    """Advance task to its subsequent processing stage."""
    service: QueueFSService = get_queuefs_service()
    try:
        return await service.advance_stage(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/tasks",
    response_model=list[QueueFSTaskResponse],
    summary="List tracked QueueFS DAG tasks",
)
async def list_queuefs_tasks(
    status_filter: SemanticTaskStatusAPI | None = Query(
        default=None,
        alias="status",
        description="Filter by task status",
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Max tasks to return"),
) -> list[QueueFSTaskResponse]:
    """List tracked tasks optionally filtered by status."""
    service: QueueFSService = get_queuefs_service()
    return service.list_tasks(status=status_filter, limit=limit)


@router.get(
    "/stats",
    response_model=QueueFSStatsResponse,
    summary="Get QueueFS queue and lock telemetry statistics",
)
async def get_queuefs_stats() -> QueueFSStatsResponse:
    """Fetch aggregated queue and lock statistics."""
    service: QueueFSService = get_queuefs_service()
    return service.get_stats()


@router.post(
    "/locks/acquire",
    response_model=AcquireLockResponse,
    summary="Acquire hierarchical path semantic lock",
)
async def acquire_path_lock(request: AcquireLockRequest) -> AcquireLockResponse:
    """Acquire a shared or exclusive lock lease over a resource path pattern."""
    service: QueueFSService = get_queuefs_service()
    try:
        return await service.acquire_lock(request)
    except LockAcquisitionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/locks/release",
    response_model=ReleaseLockResponse,
    summary="Release an active path lock lease",
)
async def release_path_lock(request: ReleaseLockRequest) -> ReleaseLockResponse:
    """Release an acquired lock lease."""
    service: QueueFSService = get_queuefs_service()
    return await service.release_lock(request)


@router.get(
    "/locks/check",
    response_model=CheckLockResponse,
    summary="Check path lock status and count active leases",
)
async def check_path_lock(
    path: str = Query(..., description="Target path to check"),
) -> CheckLockResponse:
    """Check if a specific path is covered by any active lock lease."""
    service: QueueFSService = get_queuefs_service()
    return service.check_lock(path)


__all__ = ["router"]
