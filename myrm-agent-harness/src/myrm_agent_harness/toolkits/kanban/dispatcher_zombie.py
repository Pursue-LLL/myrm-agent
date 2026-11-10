"""Zombie detection, heartbeat monitoring, scheduled task wakeup, and startup rescue mixin.

[INPUT]
- .types::KanbanTask, TaskStatus, TaskEventKind, TaskRunOutcome, BlockKind (POS: Kanban domain types.)
- .protocols::KanbanStore (POS: Protocols for the kanban toolkit.)

[OUTPUT]
- KanbanDispatcherZombieMixin: Mixin providing zombie/heartbeat/rescue/scheduled-wakeup logic.

[POS]
Zombie detection, heartbeat monitoring, scheduled wakeup, and startup orphan rescue for KanbanDispatcher.
Mixin host must provide _store, _board, _running, _task_id_to_exec, emit(), wake(), _sleep_unless_stopped().
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    KanbanBoard,
    KanbanTask,
    TaskEventKind,
    TaskRunOutcome,
    TaskStatus,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.kanban.protocols import KanbanStore

logger = get_agent_logger(__name__)


class KanbanDispatcherZombieMixin:
    """Mixin for zombie detection, heartbeat, scheduled wakeup, and startup rescue."""

    if TYPE_CHECKING:
        # Provided by KanbanDispatcher and its other mixins (the mixin host).
        _store: KanbanStore
        _board: KanbanBoard
        _running: bool
        _task_id_to_exec: dict[str, asyncio.Task[None]]

        def emit(self, event_type: str, task: KanbanTask) -> None: ...
        def wake(self) -> None: ...
        async def _sleep_unless_stopped(self, seconds: float) -> None: ...

    async def _heartbeat_loop(self, task_id: str) -> None:
        while True:
            interval = self._board.settings.heartbeat_interval_seconds
            await asyncio.sleep(interval)
            try:
                await self._store.update_heartbeat(task_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Heartbeat update failed for task %s, will retry next interval", task_id[:8], exc_info=True
                )

    async def _rescue_orphaned_tasks(self) -> None:
        """Reclaim RUNNING tasks orphaned by a prior process crash.

        Called once during ``start()`` before the dispatch/zombie loops begin.
        Uses the same ``_reclaim_task`` pipeline (retry/block/fail/event/emit)
        so behaviour is identical to zombie detection — just immediate.

        Best-effort: store errors are logged but never prevent dispatcher
        startup.
        """
        try:
            orphans = await self._store.list_running_tasks(self._board.board_id)
        except Exception:
            logger.warning("Startup rescue: failed to query running tasks, skipping", exc_info=True)
            return
        active_ids = set(self._task_id_to_exec)
        rescued = 0
        for task in orphans:
            if task.task_id in active_ids:
                continue
            try:
                await self._reclaim_task(task)
                rescued += 1
            except Exception:
                logger.warning("Startup rescue: failed to reclaim task %s", task.task_id[:8], exc_info=True)
        if rescued:
            logger.info(
                "Rescued %d orphaned task(s) on startup for board=%s",
                rescued,
                self._board.board_id,
            )

    async def _zombie_loop(self) -> None:
        while self._running:
            try:
                # Re-read settings every cycle so refresh_board() updates apply live.
                settings = self._board.settings
                check_interval = max(settings.zombie_timeout_seconds // 2, 30)
                zombies = await self._store.list_zombie_tasks(self._board.board_id, settings.zombie_timeout_seconds)
                for task in zombies:
                    logger.warning(
                        "Zombie detected: task=%s, last_heartbeat=%s",
                        task.task_id[:8],
                        task.last_heartbeat_at,
                    )
                    await self._reclaim_task(task)

                await self._wakeup_scheduled_tasks()

                await self._sleep_unless_stopped(check_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Kanban zombie loop error")
                await self._sleep_unless_stopped(check_interval)

    async def _wakeup_scheduled_tasks(self) -> None:
        """Auto-unblock tasks whose scheduled_until has passed."""
        due_tasks = await self._store.list_due_scheduled_tasks(self._board.board_id)
        block_limit = self._board.settings.block_recurrence_limit
        for task in due_tasks:
            deps_met = await self._store.are_dependencies_met(task.task_id)
            if task.block_cycle_count >= block_limit:
                target = TaskStatus.TRIAGE
                task.error = f"Escalated to triage after {task.block_cycle_count} block cycles (limit {block_limit})"
            else:
                target = TaskStatus.READY if deps_met else TaskStatus.BACKLOG
                task.error = ""
            task.status = target
            task.blocked_reason = None
            task.block_kind = None
            task.scheduled_until = None
            task.consecutive_failures = 0
            await self._store.save_task(task)
            await self._store.append_event(
                task.task_id,
                TaskEventKind.UNBLOCKED,
                payload={"source": "auto_schedule", "target": target.value},
            )
            self.emit("task_unblocked", task)
            logger.info(
                "Task %s auto-unblocked (scheduled wakeup) -> %s",
                task.task_id[:8],
                target.value,
            )
        if due_tasks:
            self.wake()

    async def _reclaim_task(self, task: KanbanTask) -> None:
        """Reclaim a zombie task: retry or fail based on budget."""
        exec_task = self._task_id_to_exec.get(task.task_id)
        if exec_task and not exec_task.done():
            exec_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await exec_task

        task.retry_count += 1
        task.consecutive_failures += 1
        task.error = "Reclaimed from zombie state (heartbeat timeout)"
        task.progress_note = None

        runs = await self._store.list_runs(task.task_id)
        active_run_id: str | None = None
        for r in reversed(runs):
            if not r.is_finished:
                active_run_id = r.run_id
                await self._store.complete_run(
                    r.run_id,
                    TaskRunOutcome.RECLAIMED,
                    error="Heartbeat timeout",
                )
                break

        await self._store.append_event(
            task.task_id,
            TaskEventKind.RECLAIMED,
            payload={"reason": "heartbeat_timeout"},
            run_id=active_run_id,
        )

        settings = self._board.settings
        if task.consecutive_failures >= settings.auto_block_after_consecutive_failures:
            task.status = TaskStatus.BLOCKED
            task.block_kind = BlockKind.HUMAN
            task.blocked_reason = f"Auto-blocked after zombie reclaim ({task.consecutive_failures} failures)"
            self.emit("task_blocked", task)
        elif task.is_retriable:
            task.status = TaskStatus.READY
            task.last_heartbeat_at = None
            self.emit("task_retrying", task)
        else:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(UTC)
            self.emit("task_failed", task)

        await self._store.save_task(task)
        self.wake()
