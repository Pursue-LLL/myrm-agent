"""[POS]: app/services/memory/queuefs_service.py
[INPUT]: API request payloads for QueueFS asynchronous DAG processing and path semantic locks.
[OUTPUT]: QueueFSService business facade coordinating harness memory QueueFS engine and locks.
"""

from myrm_agent_harness.toolkits.memory import (
    LockAcquisitionConflictError,
    PathSemanticLockManager,
    QueueFSConfig,
    QueueFSDAGEngine,
    QueueFSStats,
    SemanticDAGStage,
    SemanticDAGTask,
    SemanticLockMode,
    SemanticTaskStatus,
    TaskNotFoundError,
)

from app.schemas.queuefs import (
    AcquireLockRequest,
    AcquireLockResponse,
    CheckLockResponse,
    QueueFSStatsResponse,
    QueueFSTaskResponse,
    QueueFSTaskSubmitRequest,
    ReleaseLockRequest,
    ReleaseLockResponse,
    SemanticDAGStageAPI,
    SemanticLockModeAPI,
    SemanticTaskStatusAPI,
)


class QueueFSService:
    """Service facade managing QueueFS asynchronous DAG task scheduling and path locks."""

    def __init__(
        self,
        dag_engine: QueueFSDAGEngine | None = None,
        lock_manager: PathSemanticLockManager | None = None,
    ) -> None:
        self._lock_manager = lock_manager or PathSemanticLockManager()
        self._dag_engine = dag_engine or QueueFSDAGEngine(
            config=QueueFSConfig(),
            lock_manager=self._lock_manager,
        )

    def submit_task(self, request: QueueFSTaskSubmitRequest) -> QueueFSTaskResponse:
        """Submit a resource processing task to the DAG engine without blocking caller."""
        stages_override: list[SemanticDAGStage] | None = None
        if request.stages is not None:
            stages_override = [SemanticDAGStage(stage.value) for stage in request.stages]

        task = self._dag_engine.submit_task(
            resource_uri=request.resource_uri,
            payload=request.payload,
            stages=stages_override,
        )
        return self._task_to_response(task)

    def get_task(self, task_id: str) -> QueueFSTaskResponse | None:
        """Fetch current status and progress of a background task."""
        task = self._dag_engine.get_task(task_id)
        if task is None:
            return None
        return self._task_to_response(task)

    def list_tasks(
        self,
        status: SemanticTaskStatusAPI | None = None,
        limit: int = 50,
    ) -> list[QueueFSTaskResponse]:
        """List tasks optionally filtered by status."""
        harness_status = SemanticTaskStatus(status.value) if status is not None else None
        tasks = self._dag_engine.list_tasks(status=harness_status, limit=limit)
        return [self._task_to_response(t) for t in tasks]

    async def advance_stage(self, task_id: str) -> QueueFSTaskResponse:
        """Advance task to its next DAG pipeline stage."""
        task = await self._dag_engine.advance_stage(task_id)
        return self._task_to_response(task)

    async def execute_pipeline(self, task_id: str) -> QueueFSTaskResponse:
        """Execute full DAG pipeline for a task under path lock protection."""
        task = await self._dag_engine.execute_pipeline(task_id)
        return self._task_to_response(task)

    def get_stats(self) -> QueueFSStatsResponse:
        """Collect aggregated queue and active lock metrics."""
        stats: QueueFSStats = self._dag_engine.get_stats()
        return QueueFSStatsResponse(
            pending_tasks=stats.pending_tasks,
            running_tasks=stats.running_tasks,
            completed_tasks=stats.completed_tasks,
            failed_tasks=stats.failed_tasks,
            active_locks=stats.active_locks,
        )

    async def acquire_lock(self, request: AcquireLockRequest) -> AcquireLockResponse:
        """Acquire a fine-grained hierarchical path semantic lock lease."""
        mode = (
            SemanticLockMode.EXCLUSIVE
            if request.mode == SemanticLockModeAPI.EXCLUSIVE
            else SemanticLockMode.SHARED
        )
        lease = await self._lock_manager.acquire_lock(
            path_pattern=request.path_pattern,
            owner=request.owner,
            mode=mode,
            ttl_seconds=request.ttl_seconds,
        )
        return AcquireLockResponse(
            lock_id=lease.lock_id,
            path_pattern=lease.path_pattern,
            mode=SemanticLockModeAPI(lease.mode.value),
            owner=lease.owner,
            expires_at_epoch=lease.expires_at_epoch,
        )

    async def release_lock(self, request: ReleaseLockRequest) -> ReleaseLockResponse:
        """Release an active lock lease."""
        released = await self._lock_manager.release_lock(request.lock_id, owner=request.owner)
        return ReleaseLockResponse(released=released)

    def check_lock(self, path: str) -> CheckLockResponse:
        """Check lock state of a specific path and count active leases."""
        is_locked = self._lock_manager.is_locked(path)
        count = self._lock_manager.active_locks_count()
        return CheckLockResponse(path=path, is_locked=is_locked, active_locks_count=count)

    def _task_to_response(self, task: SemanticDAGTask) -> QueueFSTaskResponse:
        """Convert harness SemanticDAGTask to API schema response."""
        return QueueFSTaskResponse(
            task_id=task.task_id,
            resource_uri=task.resource_uri,
            payload=task.payload,
            stages=[SemanticDAGStageAPI(s.value) for s in task.stages],
            current_stage=SemanticDAGStageAPI(task.current_stage.value),
            status=SemanticTaskStatusAPI(task.status.value),
            progress_pct=task.progress_pct,
            created_at_epoch=task.created_at_epoch,
            updated_at_epoch=task.updated_at_epoch,
            error_message=task.error_message,
        )


_instance: QueueFSService | None = None


def get_queuefs_service() -> QueueFSService:
    """Singleton provider for QueueFSService."""
    global _instance
    if _instance is None:
        _instance = QueueFSService()
    return _instance


__all__ = [
    "LockAcquisitionConflictError",
    "QueueFSService",
    "TaskNotFoundError",
    "get_queuefs_service",
]
