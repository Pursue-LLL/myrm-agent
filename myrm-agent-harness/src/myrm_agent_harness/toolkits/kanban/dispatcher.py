"""Kanban dispatcher — event-driven task scheduling.

Owns the lifecycle (start/stop), manual task control (cancel, reclaim, approve, reject) and event emission.
The dispatch loop and single-task execution live in ``dispatcher_dispatch.py``; zombie/heartbeat/rescue
logic in ``dispatcher_zombie.py``; the failure pipeline in ``dispatcher_failure.py``; the success/blocked
outcome handling and dependency promotion in ``dispatcher_outcome.py``.

[INPUT]
- .types::KanbanBoard, KanbanTask, TaskStatus, BoardSettings, TaskTimeoutError (POS: Kanban domain types.)
- .protocols::KanbanStore, TaskRunner (POS: Protocols for the kanban toolkit.)
- .dispatcher_dispatch::KanbanDispatcherDispatchMixin, DispatchGate (POS: Dispatch loop and per-task execution.)
- .dispatcher_failure::KanbanDispatcherFailureMixin (POS: Failure/timeout/retry pipeline for KanbanDispatcher.)
- .dispatcher_outcome::KanbanDispatcherOutcomeMixin (POS: Success/blocked outcome handling, dependency promotion.)
- .dispatcher_zombie::KanbanDispatcherZombieMixin (POS: Zombie detection, heartbeat, rescue, scheduled wakeup.)

[OUTPUT]
- KanbanDispatcher: Event-driven multi-task scheduler.

[POS]
Kanban dispatcher — event-driven task scheduling.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.dispatcher_dispatch import (
    DispatchGate,
    KanbanDispatcherDispatchMixin,
)
from myrm_agent_harness.toolkits.kanban.dispatcher_failure import (  # noqa: F401
    _TRANSIENT_BACKOFF_SECONDS,
    _TRANSIENT_ERROR_RE,
    KanbanDispatcherFailureMixin,
)
from myrm_agent_harness.toolkits.kanban.dispatcher_outcome import KanbanDispatcherOutcomeMixin
from myrm_agent_harness.toolkits.kanban.dispatcher_zombie import (
    KanbanDispatcherZombieMixin,
)
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskEventKind,
    TaskRunOutcome,
    TaskStatus,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.kanban.protocols import (
        CompletionVerifier,
        KanbanStore,
        TaskRunner,
    )
    from myrm_agent_harness.toolkits.kanban.types import KanbanBoard

logger = get_agent_logger(__name__)

KanbanEventCallback = Callable[[str, KanbanTask], None]


class KanbanDispatcher(
    KanbanDispatcherDispatchMixin,
    KanbanDispatcherFailureMixin,
    KanbanDispatcherOutcomeMixin,
    KanbanDispatcherZombieMixin,
):
    """Event-driven multi-task scheduler.

    Lifecycle:
        dispatcher = KanbanDispatcher(store, runner, board)
        await dispatcher.start()
        ...
        await dispatcher.stop()
    """

    def __init__(
        self,
        store: KanbanStore,
        runner: TaskRunner,
        board: KanbanBoard,
        worker_id: str | None = None,
        verifier: CompletionVerifier | None = None,
        dispatch_allowed: DispatchGate | None = None,
    ) -> None:
        self._store = store
        self._runner = runner
        self._board = board
        self._worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._verifier = verifier
        self._dispatch_allowed = dispatch_allowed

        self._dispatch_task: asyncio.Task[None] | None = None
        self._zombie_task: asyncio.Task[None] | None = None
        self._running = False
        self._wake_event = asyncio.Event()
        # Set by ``stop``; ends the loops' sleeps so they can leave without being cancelled.
        self._stop_event = asyncio.Event()
        self._exec_tasks: set[asyncio.Task[None]] = set()
        self._task_id_to_exec: dict[str, asyncio.Task[None]] = {}

        self._event_callbacks: list[KanbanEventCallback] = []

    # -- Public API --

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def is_running(self) -> bool:
        return self._running

    def on_event(self, callback: KanbanEventCallback) -> None:
        """Register a callback for task lifecycle events (for SSE/EventBus)."""
        self._event_callbacks.append(callback)

    async def start(self, *, rescue_orphans: bool = True) -> None:
        """Start the dispatch and zombie-detection loops.

        ``rescue_orphans`` reclaims RUNNING tasks left by a prior crash. A caller that already
        reset them in one batch (the server does, before starting any dispatcher) passes False so
        the boot path does not issue one query per board for a result it already knows is empty.
        """
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        if rescue_orphans:
            await self._rescue_orphaned_tasks()
        self._dispatch_task = asyncio.create_task(self._dispatch_loop(), name="kanban-dispatch")
        self._zombie_task = asyncio.create_task(self._zombie_loop(), name="kanban-zombie")
        logger.info(
            "Kanban dispatcher started for board=%s worker=%s",
            self._board.board_id,
            self._worker_id,
        )

    async def stop(self, graceful_timeout: float = 30.0) -> None:
        """Stop the loops at their next iteration boundary, then wait for executing tasks to finish."""
        self._running = False
        self._wake_event.set()
        self._stop_event.set()
        await self._join_loops()

        if self._exec_tasks:
            logger.info(
                "Waiting for %d executing tasks (timeout=%.0fs)",
                len(self._exec_tasks),
                graceful_timeout,
            )
            _done, pending = await asyncio.wait(
                self._exec_tasks,
                timeout=graceful_timeout,
            )
            for t in pending:
                t.cancel()
            if pending:
                logger.warning(
                    "%d tasks did not finish within %.0fs, cancelled",
                    len(pending),
                    graceful_timeout,
                )

        logger.info("Kanban dispatcher stopped for board=%s", self._board.board_id)

    def wake(self) -> None:
        """Signal the dispatcher to check for new tasks immediately."""
        self._wake_event.set()

    def refresh_board(self, board: KanbanBoard) -> None:
        """Hot-swap the board so runtime settings changes take effect live.

        The dispatch and zombie loops re-read ``self._board.settings`` on every
        iteration, so a refreshed ``max_concurrent_tasks`` / ``zombie_timeout_seconds``
        applies on the next wake cycle while tasks already executing keep running
        untouched — no restart required.
        """
        if board.board_id != self._board.board_id:
            raise ValueError(
                f"refresh_board board id mismatch: expected {self._board.board_id!r}, got {board.board_id!r}"
            )
        self._board = board
        self.wake()

    async def cancel_execution(self, task_id: str) -> bool:
        """Cancel the asyncio.Task executing a kanban task without modifying task state.

        Returns True if a running execution was cancelled, False if the task
        was not being executed by this dispatcher.
        """
        exec_task = self._task_id_to_exec.get(task_id)
        if exec_task is None or exec_task.done():
            return False

        exec_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await exec_task
        return True

    async def reclaim_task(self, task_id: str, reason: str | None = None) -> bool:
        """Manually reclaim a running task: cancel its worker, close the run,
        reset to READY so the dispatcher can re-schedule it.

        Returns True if a running worker was cancelled, False if the task
        was not being executed by this dispatcher.
        """
        exec_task = self._task_id_to_exec.get(task_id)
        if exec_task is None or exec_task.done():
            return False

        exec_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await exec_task

        task = await self._store.get_task(task_id)
        if task is None:
            return True

        runs = await self._store.list_runs(task_id)
        active_run_id: str | None = None
        for r in reversed(runs):
            if not r.is_finished:
                active_run_id = r.run_id
                await self._store.complete_run(
                    r.run_id,
                    TaskRunOutcome.RECLAIMED,
                    error=f"manual_reclaim: {reason or 'user request'}",
                )
                break

        task.status = TaskStatus.READY
        task.consecutive_failures = 0
        task.error = ""
        task.last_heartbeat_at = task.progress_note = None
        task.blocked_reason = task.block_kind = task.scheduled_until = None
        await self._store.save_task(task)
        await self._store.append_event(
            task_id,
            TaskEventKind.RECLAIMED,
            payload={"manual": True, "reason": reason or "user request"},
            run_id=active_run_id,
        )
        self.emit("task_reclaimed", task)
        self.wake()
        logger.info(
            "Task %s manually reclaimed: %s",
            task_id[:8],
            reason or "user request",
        )
        return True

    async def approve_task(
        self,
        task_id: str,
        *,
        approver: str | None = None,
    ) -> KanbanTask | None:
        """Approve an IN_REVIEW task: promote it to COMPLETED and release dependents.

        Operator-driven (REST/GUI) — there is no LLM tool for approval.
        Atomic compare-and-swap on IN_REVIEW makes double-submits idempotent:
        a task that already left IN_REVIEW is returned unchanged (no-op).
        """
        task = await self._store.transition_task_status(
            task_id,
            TaskStatus.IN_REVIEW,
            TaskStatus.COMPLETED,
        )
        if task is None:
            return await self._store.get_task(task_id)

        task.completed_at = datetime.now(UTC)
        task.consecutive_failures = 0
        task.block_cycle_count = 0
        task.error = ""
        task.progress_note = None
        await self._store.save_task(task)
        await self._store.append_event(
            task_id,
            TaskEventKind.APPROVED,
            payload={"approver": approver or "human"},
        )
        self.emit("task_completed", task)
        await self._promote_dependents(task_id)
        self.wake()
        logger.info("Task %s approved and completed", task_id[:8])
        return task

    async def reject_task(
        self,
        task_id: str,
        *,
        reason: str = "",
        approver: str | None = None,
    ) -> KanbanTask | None:
        """Reject an IN_REVIEW task: send it back to READY for rework.

        The rejection reason is persisted on the event trail and surfaced in
        the worker context under `## Review history` (via context_builder) so a
        re-run adapts. Atomic compare-and-swap on IN_REVIEW keeps double-submits
        idempotent.
        """
        task = await self._store.transition_task_status(
            task_id,
            TaskStatus.IN_REVIEW,
            TaskStatus.READY,
        )
        if task is None:
            return await self._store.get_task(task_id)

        task.consecutive_failures = 0
        task.retry_count = 0
        task.error = reason
        task.last_heartbeat_at = None
        task.progress_note = None
        await self._store.save_task(task)
        await self._store.append_event(
            task_id,
            TaskEventKind.REJECTED,
            payload={
                "reason": reason,
                "approver": approver or "human",
                "from": TaskStatus.IN_REVIEW.value,
            },
        )
        self.emit("task_rejected", task)
        self.wake()
        logger.info("Task %s rejected for rework: %s", task_id[:8], reason)
        return task

    # -- Event emission --

    def emit(self, event_type: str, task: KanbanTask) -> None:
        """Emit a lifecycle event to all registered callbacks."""
        for cb in self._event_callbacks:
            try:
                cb(event_type, task)
            except Exception:
                logger.exception("Kanban event callback error")
