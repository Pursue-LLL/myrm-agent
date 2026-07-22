"""Task worker for async task execution.

[INPUT]
- myrm_agent_harness.toolkits.tasks::{Task, TaskStore, TaskStatus, TaskError} (POS: Queue protocol + persistence contract)
- app/tasks/executors/*::_TaskExecutor impl (POS: Task-type specific execution capability)
- TaskEventCallback (POS: Task status propagation bridge to SSE/event bus layer)

[OUTPUT]
- TaskWorker: server-side async task consumer with retry, timeout, cancellation, and status callbacks.

[POS]
- Business orchestration runtime for the task queue. It executes pending media jobs,
  persists lifecycle transitions, and emits state updates consumed by API/SSE surfaces.
"""

import asyncio
import logging
import traceback
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Protocol

from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    Task,
    TaskError,
    TaskFilters,
    TaskStatus,
    TaskStore,
)

logger = logging.getLogger(__name__)

type TaskEventCallback = Callable[[str, TaskStatus, dict[str, object] | None], Coroutine[object, object, None]]


class _TaskExecutor(Protocol):
    def can_execute(self, task_type: str) -> bool: ...

    async def execute(self, task: Task) -> object: ...


class TaskWorker:
    """Worker that consumes and executes tasks.

    Features:
    - Priority-based task consumption
    - Concurrency control (prevents OOM)
    - Timeout handling
    - Cancellation support
    - Result caching
    - Automatic retry
    - Progress tracking
    - Worker health monitoring
    - Real-time event emission via callback
    """

    def __init__(
        self,
        store: TaskStore,
        executors: list[_TaskExecutor],
        max_concurrency: int = 3,
        worker_id: str = "worker-1",
        on_status_change: TaskEventCallback | None = None,
    ) -> None:
        self._store = store
        self._executors: dict[_TaskExecutor, _TaskExecutor] = {e: e for e in executors}
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._worker_id = worker_id
        self._running = False
        self._on_status_change = on_status_change

    async def _emit_event(self, task: Task, status: TaskStatus, error: TaskError | None = None) -> None:
        """Emit task status change event via callback."""
        if not self._on_status_change:
            return

        data: dict[str, object] = {
            "task_type": task.task_type,
            "progress": task.progress,
        }
        if error:
            data["error"] = {"error_type": error.error_type, "message": error.message, "recoverable": error.recoverable.value}

        try:
            await self._on_status_change(task.task_id, status, data)
        except Exception as e:
            logger.warning(f"Failed to emit task event: {e}")

    async def start(self) -> None:
        """Start worker main loop."""
        self._running = True
        logger.info(f"TaskWorker {self._worker_id} starting...")

        try:
            await self._run_loop()
        except Exception as e:
            logger.error(f"TaskWorker {self._worker_id} crashed: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """Stop worker gracefully."""
        logger.info(f"TaskWorker {self._worker_id} stopping...")
        self._running = False

    async def _run_loop(self) -> None:
        """Main worker loop."""
        while self._running:
            try:
                # Query pending tasks (priority-based)
                tasks = await self._store.list_tasks(
                    TaskFilters(
                        status=TaskStatus.PENDING,
                        limit=10,
                        order_by="priority DESC, created_at ASC",
                    )
                )

                if not tasks:
                    await asyncio.sleep(1)
                    continue

                # Execute tasks concurrently (within semaphore limit)
                await asyncio.gather(*[self._execute_task(task) for task in tasks], return_exceptions=True)

            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _execute_task(self, task: Task) -> None:
        """Execute single task with timeout and error handling."""
        async with self._semaphore:
            try:
                # Check result cache
                if task.cache_key:
                    cached = await self._store.find_by_cache_key(task.cache_key)
                    if cached and cached.status == TaskStatus.SUCCEEDED:
                        logger.info(f"Task {task.task_id} cache hit: {task.cache_key}")
                        await self._reuse_cached_result(task, cached)
                        return

                # Find executor
                executor = self._find_executor(task.task_type)
                if not executor:
                    logger.error(f"No executor for task type: {task.task_type}")
                    await self._handle_no_executor(task)
                    return

                # Mark as running
                task.mark_started(self._worker_id)
                await self._store.update_task(
                    task.task_id,
                    status=TaskStatus.RUNNING,
                    started_at=task.started_at,
                    worker_id=self._worker_id,
                    worker_heartbeat_at=task.worker_heartbeat_at,
                )
                await self._emit_event(task, TaskStatus.RUNNING)

                logger.info(f"Task {task.task_id} started (priority={task.priority})")

                # Execute with timeout
                result = await asyncio.wait_for(
                    executor.execute(task),
                    timeout=task.timeout,
                )

                # Mark as succeeded
                task.mark_succeeded(result)
                await self._store.update_task(
                    task.task_id,
                    status=TaskStatus.SUCCEEDED,
                    result=result,
                    progress=1.0,
                    completed_at=task.completed_at,
                )
                await self._emit_event(task, TaskStatus.SUCCEEDED)

                logger.info(f"Task {task.task_id} succeeded")

            except asyncio.TimeoutError:
                logger.warning(f"Task {task.task_id} timeout after {task.timeout}s")
                await self._handle_timeout(task)

            except asyncio.CancelledError:
                logger.info(f"Task {task.task_id} cancelled")
                await self._handle_cancellation(task)

            except Exception as e:
                logger.error(f"Task {task.task_id} failed: {e}", exc_info=True)
                await self._handle_failure(task, e)

    async def _reuse_cached_result(self, task: Task, cached: Task) -> None:
        """Reuse cached task result."""
        await self._store.update_task(
            task.task_id,
            status=TaskStatus.SUCCEEDED,
            result=cached.result,
            progress=1.0,
            completed_at=datetime.now(UTC),
        )
        task.progress = 1.0
        await self._emit_event(task, TaskStatus.SUCCEEDED)

    async def _handle_timeout(self, task: Task) -> None:
        """Handle task timeout."""
        error = TaskError(
            error_type="timeout",
            message=f"Task exceeded timeout of {task.timeout}s",
            recoverable=ErrorRecoverability.PERMANENT,
        )

        await self._store.update_task(
            task.task_id,
            status=TaskStatus.FAILED,
            error=error,
            completed_at=datetime.now(UTC),
        )
        await self._emit_event(task, TaskStatus.FAILED, error)

    async def _handle_cancellation(self, task: Task) -> None:
        """Handle task cancellation."""
        await self._store.update_task(
            task.task_id,
            status=TaskStatus.CANCELLED,
            cancellation_reason=task.cancellation_reason or "User cancelled",
            completed_at=datetime.now(UTC),
        )
        await self._emit_event(task, TaskStatus.CANCELLED)

    async def _handle_failure(self, task: Task, exception: Exception) -> None:
        """Handle task failure with retry logic."""
        # Classify error recoverability
        recoverable = self._classify_error(exception)

        error = TaskError(
            error_type=type(exception).__name__,
            message=str(exception),
            recoverable=recoverable,
            traceback="".join(traceback.format_exception(exception)),
        )

        # Auto-retry runs while task is still in RUNNING state, so worker retry
        # eligibility must not depend on Task.can_retry()'s FAILED-status guard.
        if self._should_auto_retry(task, recoverable):
            task.retry_count += 1
            delay = task.retry_policy.get_delay(task.retry_count)
            task.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
            task.status = TaskStatus.PENDING
            task.error = error

            logger.info(
                f"Task {task.task_id} will retry in {delay}s (attempt {task.retry_count}/{task.retry_policy.max_retries})"
            )

            await self._store.update_task(
                task.task_id,
                status=TaskStatus.PENDING,  # Reset to pending for retry
                error=error,
                retry_count=task.retry_count,
                next_retry_at=task.next_retry_at,
            )
            await self._emit_event(task, TaskStatus.PENDING)
        else:
            # No more retries, mark as failed
            await self._store.update_task(
                task.task_id,
                status=TaskStatus.FAILED,
                error=error,
                completed_at=datetime.now(UTC),
            )
            await self._emit_event(task, TaskStatus.FAILED, error)

    def _should_auto_retry(self, task: Task, recoverable: ErrorRecoverability) -> bool:
        """Check retry eligibility for worker-side failure handling."""
        if recoverable != ErrorRecoverability.TRANSIENT:
            return False
        if not task.retry_policy:
            return False
        return task.retry_count < task.retry_policy.max_retries

    async def _handle_no_executor(self, task: Task) -> None:
        """Handle missing executor."""
        error = TaskError(
            error_type="no_executor",
            message=f"No executor found for task type: {task.task_type}",
            recoverable=ErrorRecoverability.PERMANENT,
        )

        await self._store.update_task(
            task.task_id,
            status=TaskStatus.FAILED,
            error=error,
            completed_at=datetime.now(UTC),
        )
        await self._emit_event(task, TaskStatus.FAILED, error)

    def _find_executor(self, task_type: str) -> _TaskExecutor | None:
        """Find executor that can handle task type."""
        for executor in self._executors:
            if executor.can_execute(task_type):
                return executor
        return None

    def _classify_error(self, exception: Exception) -> ErrorRecoverability:
        """Classify error as transient or permanent."""
        # Network errors, timeouts, overloads are transient
        transient_types = (
            "ConnectionError",
            "TimeoutError",
            "HTTPError",
            "RateLimitError",
            "ServiceUnavailable",
        )

        exc_name = type(exception).__name__
        if exc_name in transient_types:
            return ErrorRecoverability.TRANSIENT

        # Validation, auth, not found are permanent
        permanent_types = (
            "ValidationError",
            "AuthenticationError",
            "PermissionError",
            "NotFoundError",
        )

        if exc_name in permanent_types:
            return ErrorRecoverability.PERMANENT

        # Default to transient (allow retry)
        return ErrorRecoverability.TRANSIENT


__all__ = ["TaskEventCallback", "TaskWorker"]
