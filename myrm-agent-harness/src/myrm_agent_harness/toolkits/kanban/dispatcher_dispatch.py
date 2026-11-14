"""Dispatch loop and single-task execution for KanbanDispatcher.

[INPUT]
- .types::BlockKind, TaskStatus, TaskTimeoutError, TaskExecutionResult (POS: Kanban domain types.)
- .protocols::KanbanStore, TaskRunner (POS: Protocols for the kanban toolkit.)

[OUTPUT]
- KanbanDispatcherDispatchMixin: dispatch loop (claim → execute), wake handling, per-task bookkeeping guard.

[POS]
Dispatch loop half of KanbanDispatcher. The loop asks the injected dispatch gate before claiming, so a
server with no usable model configuration leaves READY tasks queued instead of failing them in a burst
at boot; execution bookkeeping failures are absorbed into one log line per task. Stopping the dispatcher
ends the loops at an iteration boundary (never inside a store call) with cancellation as a bounded fallback.
Mixin host must provide the state and handlers declared in the class body.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    TaskEventKind,
    TaskExecutionResult,
    TaskStatus,
    TaskTimeoutError,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from datetime import datetime

    from myrm_agent_harness.toolkits.kanban.protocols import KanbanStore, TaskRunner
    from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask

logger = get_agent_logger(__name__)

# Returns True when a task may be claimed right now (server: a usable model configuration exists).
DispatchGate = Callable[[], Awaitable[bool]]

# How long a loop gets to reach its next iteration boundary once the dispatcher is stopped, and again after the
# cancellation fallback, before it is abandoned.
_LOOP_EXIT_GRACE_SECONDS = 5.0


class KanbanDispatcherDispatchMixin:
    """Mixin for the dispatch loop and single-task execution."""

    if TYPE_CHECKING:
        # Provided by KanbanDispatcher and its other mixins (the mixin host).
        _store: KanbanStore
        _runner: TaskRunner
        _board: KanbanBoard
        _worker_id: str
        _running: bool
        _wake_event: asyncio.Event
        _stop_event: asyncio.Event
        _dispatch_allowed: DispatchGate | None
        _dispatch_task: asyncio.Task[None] | None
        _zombie_task: asyncio.Task[None] | None
        _exec_tasks: set[asyncio.Task[None]]
        _task_id_to_exec: dict[str, asyncio.Task[None]]

        def emit(self, event_type: str, task: KanbanTask) -> None: ...
        async def _heartbeat_loop(self, task_id: str) -> None: ...
        async def _handle_success(self, task_id: str, result: str, run_id: str) -> None: ...
        async def _handle_blocked(
            self,
            task_id: str,
            reason: str,
            run_id: str,
            *,
            block_kind: BlockKind = ...,
            scheduled_until: datetime | None = ...,
            metadata_patch: dict[str, object] | None = ...,
        ) -> None: ...
        async def _handle_failure(self, task_id: str, error: str, run_id: str) -> None: ...
        async def _handle_timeout(
            self,
            task_id: str,
            error: str,
            run_id: str,
            *,
            elapsed_seconds: float,
            limit_seconds: int,
        ) -> None: ...

    # -- Dispatch loop --

    async def _dispatch_loop(self) -> None:
        while self._running:
            try:
                # Re-read settings every iteration so refresh_board() runtime
                # board-config updates apply on the next wake cycle.
                settings = self._board.settings
                # Clear before checking so wake() signals arriving during
                # claim are not lost — the next wait() returns immediately.
                self._wake_event.clear()

                if self._dispatch_allowed is not None and not await self._dispatch_allowed():
                    # No usable model configuration: leaving READY tasks untouched is the point —
                    # claiming them would fail every task and write 390 failure rows on every boot.
                    await self._wait_for_wake(settings.heartbeat_interval_seconds)
                    continue

                running_count = len(await self._store.list_running_tasks(self._board.board_id))
                available_slots = settings.max_concurrent_tasks - running_count

                if available_slots > 0 and self._running:
                    ready_tasks = await self._store.list_ready_tasks(self._board.board_id)
                    for task in ready_tasks[:available_slots]:
                        if not self._running:
                            # Stopped while claiming: take no further work, the loop ends at this boundary.
                            break
                        claimed = await self._store.claim_task(task.task_id, self._worker_id)
                        if claimed:
                            t = asyncio.create_task(
                                self._execute_task(task.task_id),
                                name=f"kanban-exec-{task.task_id[:8]}",
                            )
                            self._exec_tasks.add(t)
                            self._task_id_to_exec[task.task_id] = t

                            def _on_exec_done(
                                fut: asyncio.Task[None],
                                tid: str = task.task_id,
                            ) -> None:
                                self._exec_tasks.discard(fut)
                                self._task_id_to_exec.pop(tid, None)

                            t.add_done_callback(_on_exec_done)

                await self._wait_for_wake(settings.heartbeat_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Kanban dispatch loop error")
                await self._sleep_unless_stopped(5)

    async def _wait_for_wake(self, timeout_seconds: float) -> None:
        """Block until ``wake()`` or the heartbeat interval, whichever comes first."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake_event.wait(), timeout=timeout_seconds)

    async def _sleep_unless_stopped(self, seconds: float) -> None:
        """Sleep for ``seconds``, returning early once the dispatcher is stopped."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)

    async def _join_loops(self) -> None:
        """End the dispatch and zombie loops without interrupting a store call.

        Once the dispatcher is stopped each loop leaves at its next iteration boundary, so a store call in flight
        completes first: cancelling a loop inside a database call aborts the call, and the connection's teardown
        that follows can wait forever, which would block the stop itself. A loop still running after the grace
        period is cancelled; one that outlives the cancellation too is abandoned with a warning so that
        ``stop`` always returns.
        """
        loops = {task for task in (self._dispatch_task, self._zombie_task) if task is not None}
        self._dispatch_task = None
        self._zombie_task = None
        if not loops:
            return
        _, pending = await asyncio.wait(loops, timeout=_LOOP_EXIT_GRACE_SECONDS)
        if not pending:
            return
        for task in pending:
            task.cancel()
        _, abandoned = await asyncio.wait(pending, timeout=_LOOP_EXIT_GRACE_SECONDS)
        if abandoned:
            logger.warning(
                "%d kanban loop(s) of board=%s did not end after cancellation; abandoned",
                len(abandoned),
                self._board.board_id,
            )

    async def _execute_task(self, task_id: str) -> None:
        """Execute a single task, absorbing bookkeeping failures.

        A failed write while recording a failure (SQLite lock contention under a burst of tasks)
        must not escape here: it would surface as asyncio's "Task exception was never retrieved" and
        bury the real cause under hundreds of stack traces. One line names the task instead.
        """
        try:
            await self._execute_task_inner(task_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Kanban task %s bookkeeping failed: %s", task_id[:8], exc)

    async def _execute_task_inner(self, task_id: str) -> None:
        """Run one claimed task: run tracking, heartbeat, outcome routing."""
        task = await self._store.get_task(task_id)
        if task is None:
            return
        if task.status != TaskStatus.RUNNING:
            logger.warning(
                "Task %s status drifted to %s after claim, aborting execution",
                task_id[:8],
                task.status.value,
            )
            return

        run = await self._store.create_run(task_id, self._worker_id)
        await self._store.append_event(
            task_id,
            TaskEventKind.CLAIMED,
            payload={"worker_id": self._worker_id},
            run_id=run.run_id,
        )
        self.emit("task_started", task)

        heartbeat_handle = asyncio.create_task(
            self._heartbeat_loop(task_id),
            name=f"kanban-hb-{task_id[:8]}",
        )

        try:
            exec_output = await self._runner.run(task)
            heartbeat_handle.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_handle

            if isinstance(exec_output, TaskExecutionResult):
                if exec_output.is_success:
                    await self._handle_success(task_id, exec_output.message, run.run_id)
                elif exec_output.is_blocked:
                    await self._handle_blocked(
                        task_id,
                        exec_output.blocked_reason or exec_output.message,
                        run.run_id,
                        block_kind=exec_output.block_kind or BlockKind.HUMAN,
                        scheduled_until=exec_output.scheduled_until,
                        metadata_patch=exec_output.metadata_patch,
                    )
                else:
                    await self._handle_failure(task_id, exec_output.message, run.run_id)
            else:
                success, result_text = exec_output
                if success:
                    await self._handle_success(task_id, result_text, run.run_id)
                else:
                    # If task was already marked BLOCKED by the runner, route to blocked handler
                    fresh_task = await self._store.get_task(task_id)
                    if fresh_task and fresh_task.status == TaskStatus.BLOCKED:
                        await self._handle_blocked(
                            task_id,
                            fresh_task.blocked_reason or result_text,
                            run.run_id,
                            block_kind=fresh_task.block_kind or BlockKind.HUMAN,
                            scheduled_until=fresh_task.scheduled_until,
                        )
                    else:
                        await self._handle_failure(task_id, result_text, run.run_id)
        except asyncio.CancelledError:
            heartbeat_handle.cancel()
            raise
        except TaskTimeoutError as exc:
            heartbeat_handle.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_handle
            await self._handle_timeout(
                task_id,
                str(exc),
                run.run_id,
                elapsed_seconds=exc.elapsed_seconds,
                limit_seconds=exc.limit_seconds,
            )
        except Exception as exc:
            heartbeat_handle.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_handle
            await self._handle_failure(task_id, str(exc), run.run_id)
