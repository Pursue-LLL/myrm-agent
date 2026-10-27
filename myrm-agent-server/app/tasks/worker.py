"""Task worker for async media task execution.

[INPUT]
- myrm_agent_harness.toolkits.tasks::{Task, TaskStore, TaskStatus, TaskError, TaskFilters} (POS: Queue protocol + compare-and-set persistence contract)
- app/tasks/executors/*::TaskExecutor impl (POS: Task-type specific execution capability)
- TaskEventCallback (POS: Task status propagation bridge to SSE/event bus layer)

[OUTPUT]
- TaskWorker: server-side async task consumer with a bounded in-flight set, timeout, abort, restart recovery and status callbacks.

[POS]
- Business orchestration runtime for the task queue. It claims pending media jobs in priority order,
  settles each one exactly once (the first terminal write wins), and emits state updates consumed by API/SSE surfaces.
"""

import asyncio
import contextlib
import logging
import traceback
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Protocol

from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    Task,
    TaskError,
    TaskFilters,
    TaskStatus,
    TaskStore,
)

from app.tasks.metrics import (
    task_cancelled_total,
    task_duration_seconds,
    task_failed_total,
    task_succeeded_total,
    task_timeout_total,
)

logger = logging.getLogger(__name__)

type TaskEventCallback = Callable[[str, TaskStatus, dict[str, object] | None], Coroutine[object, object, None]]

_POLL_INTERVAL_SECONDS = 1.0
_STOP_GRACE_SECONDS = 5.0
_SWEEP_BATCH_SIZE = 100
_QUEUE_ORDER = "priority DESC, created_at ASC"

_PERMANENT_ERROR_TYPES = frozenset({"ValidationError", "AuthenticationError", "PermissionError", "NotFoundError"})


class TaskExecutor(Protocol):
    def can_execute(self, task_type: str) -> bool: ...

    async def execute(self, task: Task) -> object: ...


def _interrupted_error() -> TaskError:
    return TaskError(
        error_type="interrupted",
        message="The task was interrupted before it finished because the app stopped. It can be retried.",
        recoverable=ErrorRecoverability.TRANSIENT,
    )


def _classify_error(exception: Exception) -> ErrorRecoverability:
    """Classify an executor failure; anything not known to be permanent stays retryable by the user."""
    if type(exception).__name__ in _PERMANENT_ERROR_TYPES:
        return ErrorRecoverability.PERMANENT
    return ErrorRecoverability.TRANSIENT


class TaskWorker:
    """Claims pending tasks into at most ``max_concurrency`` in-flight runs and settles each exactly once.

    Every state change is a compare-and-set on the current status, so a user cancel and a finishing run
    can never overwrite each other: whichever terminal write lands first stands.
    """

    def __init__(
        self,
        store: TaskStore,
        executors: list[TaskExecutor],
        max_concurrency: int = 3,
        worker_id: str = "worker-1",
        on_status_change: TaskEventCallback | None = None,
    ) -> None:
        self._store = store
        self._executors = tuple(executors)
        self._max_concurrency = max_concurrency
        self._worker_id = worker_id
        self._on_status_change = on_status_change
        self._running = False
        self._in_flight: dict[str, asyncio.Task[None]] = {}
        self._wake = asyncio.Event()

    @staticmethod
    def _safe_counter_inc(counter: object, **labels: str) -> None:
        """Best-effort metric increment that never blocks task execution."""
        try:
            counter.labels(**labels).inc()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive metrics guard
            logger.debug("Failed to increment task metric: %s", exc)

    @staticmethod
    def _safe_histogram_observe(histogram: object, value: float, **labels: str) -> None:
        """Best-effort histogram observe that never blocks task execution."""
        try:
            histogram.labels(**labels).observe(value)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive metrics guard
            logger.debug("Failed to observe task metric: %s", exc)

    def _observe_duration(self, task: Task, status: TaskStatus) -> None:
        """Record task execution duration when start time is available."""
        if task.started_at is None:
            return
        elapsed_seconds = (datetime.now(UTC) - task.started_at).total_seconds()
        if elapsed_seconds < 0:
            return
        self._safe_histogram_observe(
            task_duration_seconds,
            elapsed_seconds,
            task_type=task.task_type,
            status=status.value,
        )

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
        """Recover tasks orphaned by the previous process, then run the claim loop until ``stop()``."""
        self._running = True
        logger.info(f"TaskWorker {self._worker_id} starting...")

        try:
            await self._fail_orphaned_running()
            await self._run_loop()
        except Exception as e:
            logger.error(f"TaskWorker {self._worker_id} crashed: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """Stop claiming, then interrupt every in-flight run; each run marks its own task interrupted."""
        logger.info(f"TaskWorker {self._worker_id} stopping...")
        self._running = False
        self._wake.set()

        runs = list(self._in_flight.values())
        for run in runs:
            run.cancel()
        if runs:
            _, pending = await asyncio.wait(runs, timeout=_STOP_GRACE_SECONDS)
            if pending:
                logger.warning(f"TaskWorker {self._worker_id}: {len(pending)} run(s) did not stop within the grace period")

    def abort(self, task_id: str) -> bool:
        """Interrupt the in-flight run of *task_id*; the caller owns writing the CANCELLED row.

        Returns False when the task is not currently executing here (queued, or already settled).
        """
        run = self._in_flight.get(task_id)
        if run is None:
            return False
        run.cancel()
        return True

    async def _run_loop(self) -> None:
        """Refill free slots from the queue; wake early when a run finishes."""
        while self._running:
            self._wake.clear()
            try:
                await self._claim_available()
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=_POLL_INTERVAL_SECONDS)

    async def _claim_available(self) -> None:
        """Claim pending tasks (priority, then FIFO) until every slot is busy or the queue is empty."""
        while self._running and (free := self._max_concurrency - len(self._in_flight)) > 0:
            pending = await self._store.list_tasks(TaskFilters(status=TaskStatus.PENDING, limit=free, order_by=_QUEUE_ORDER))
            if not pending:
                return
            for candidate in pending:
                now = datetime.now(UTC)
                claimed = await self._store.update_task_if_status(
                    candidate.task_id,
                    (TaskStatus.PENDING,),
                    status=TaskStatus.RUNNING,
                    started_at=now,
                    worker_id=self._worker_id,
                    worker_heartbeat_at=now,
                )
                if claimed is not None:
                    self._spawn(claimed)

    def _spawn(self, task: Task) -> None:
        run = asyncio.create_task(self._run(task), name=f"media-task-{task.task_id}")
        self._in_flight[task.task_id] = run
        run.add_done_callback(lambda finished: self._on_run_done(task.task_id, finished))

    def _on_run_done(self, task_id: str, run: asyncio.Task[None]) -> None:
        self._in_flight.pop(task_id, None)
        self._wake.set()
        if not run.cancelled() and (error := run.exception()) is not None:
            logger.error(f"Task {task_id} run crashed: {error}", exc_info=error)

    async def _run(self, task: Task) -> None:
        """Execute one claimed task and settle it."""
        executor = self._find_executor(task.task_type)
        if executor is None:
            logger.error(f"No executor for task type: {task.task_type}")
            await self._settle_failed(
                task,
                TaskError(
                    error_type="no_executor",
                    message=f"No executor found for task type: {task.task_type}",
                    recoverable=ErrorRecoverability.PERMANENT,
                ),
            )
            return

        await self._emit_event(task, TaskStatus.RUNNING)
        logger.info(f"Task {task.task_id} started (priority={task.priority})")

        try:
            result = await asyncio.wait_for(executor.execute(task), timeout=task.timeout)
        except TimeoutError:
            logger.warning(f"Task {task.task_id} timeout after {task.timeout}s")
            await self._settle_failed(
                task,
                TaskError(
                    error_type="timeout",
                    message=f"Task exceeded timeout of {task.timeout}s",
                    recoverable=ErrorRecoverability.PERMANENT,
                ),
                timed_out=True,
            )
        except asyncio.CancelledError:
            await self._settle_cancelled(task)
            raise
        except Exception as exc:
            logger.error(f"Task {task.task_id} failed: {exc}", exc_info=True)
            await self._settle_failed(
                task,
                TaskError(
                    error_type=type(exc).__name__,
                    message=str(exc),
                    recoverable=_classify_error(exc),
                    traceback="".join(traceback.format_exception(exc)),
                ),
            )
        else:
            await self._settle_succeeded(task, result)

    async def _finish(self, task: Task, status: TaskStatus, **fields: object) -> Task | None:
        """Write the terminal state only while the task is still RUNNING; None means someone else settled it first."""
        settled = await self._store.update_task_if_status(
            task.task_id,
            (TaskStatus.RUNNING,),
            status=status,
            completed_at=datetime.now(UTC),
            **fields,
        )
        if settled is None:
            logger.info(f"Task {task.task_id} was already settled; dropping its {status.value} outcome")
        return settled

    async def _settle_succeeded(self, task: Task, result: object) -> None:
        settled = await self._finish(task, TaskStatus.SUCCEEDED, result=result, progress=1.0)
        if settled is None:
            return
        await self._emit_event(settled, TaskStatus.SUCCEEDED)
        self._safe_counter_inc(task_succeeded_total, task_type=task.task_type)
        self._observe_duration(task, TaskStatus.SUCCEEDED)
        logger.info(f"Task {task.task_id} succeeded")

    async def _settle_failed(
        self,
        task: Task,
        error: TaskError,
        *,
        timed_out: bool = False,
        observe_duration: bool = True,
    ) -> None:
        settled = await self._finish(task, TaskStatus.FAILED, error=error)
        if settled is None:
            return
        await self._emit_event(settled, TaskStatus.FAILED, error)
        if timed_out:
            self._safe_counter_inc(task_timeout_total, task_type=task.task_type)
        self._safe_counter_inc(task_failed_total, task_type=task.task_type, error_type=error.error_type)
        if observe_duration:
            self._observe_duration(task, TaskStatus.FAILED)

    async def _settle_cancelled(self, task: Task) -> None:
        """A run was cancelled: on shutdown mark it interrupted; after ``abort`` the canceller already wrote CANCELLED."""
        logger.info(f"Task {task.task_id} cancelled")
        if not self._running:
            await self._settle_failed(task, _interrupted_error())
            return
        self._safe_counter_inc(task_cancelled_total, task_type=task.task_type)
        self._observe_duration(task, TaskStatus.CANCELLED)

    async def _fail_orphaned_running(self) -> None:
        """Fail tasks a previous process left RUNNING (nothing can be executing them before the first claim)."""
        try:
            while orphans := await self._store.list_tasks(TaskFilters(status=TaskStatus.RUNNING, limit=_SWEEP_BATCH_SIZE)):
                for orphan in orphans:
                    # The recorded start belongs to a dead process, so its age says nothing about run time.
                    await self._settle_failed(orphan, _interrupted_error(), observe_duration=False)
                logger.warning(f"Marked {len(orphans)} orphaned running task(s) as interrupted")
        except Exception as e:
            logger.error(f"Failed to recover orphaned running tasks: {e}", exc_info=True)

    def _find_executor(self, task_type: str) -> TaskExecutor | None:
        """Find executor that can handle task type."""
        return next((executor for executor in self._executors if executor.can_execute(task_type)), None)


__all__ = ["TaskEventCallback", "TaskExecutor", "TaskWorker"]
