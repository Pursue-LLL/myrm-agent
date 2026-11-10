"""Kanban dispatcher outcome handling — success, intentional block, dependent promotion.

[INPUT]
- kanban.types::BlockKind, KanbanTask, TaskEventKind, TaskRunOutcome, TaskStatus (POS: domain types)
- kanban.types::clear_completion_intent, has_completion_intent (POS: completion-intent metadata helpers)
- kanban.protocols::KanbanStore, CompletionVerifier (POS: persistence and verification protocols)

[OUTPUT]
- KanbanDispatcherOutcomeMixin: _handle_success / _handle_blocked / _promote_dependents

[POS]
Outcome pipeline of a finished execution for KanbanDispatcher — completion verification, review submission,
completion with dependent promotion, and intentional BLOCKED transitions.
Mixin host must provide _store, _verifier, emit(), wake(), _handle_failure().
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    KanbanTask,
    TaskEventKind,
    TaskRunOutcome,
    TaskStatus,
    clear_completion_intent,
    has_completion_intent,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.kanban.protocols import CompletionVerifier, KanbanStore

logger = get_agent_logger(__name__)


class KanbanDispatcherOutcomeMixin:
    """Outcome handling of a finished task execution for KanbanDispatcher."""

    if TYPE_CHECKING:
        # Provided by KanbanDispatcher (the mixin host).
        _store: KanbanStore
        _verifier: CompletionVerifier | None

        def emit(self, event_type: str, task: KanbanTask) -> None: ...
        def wake(self) -> None: ...
        async def _handle_failure(self, task_id: str, error: str, run_id: str) -> None: ...

    async def _handle_success(
        self,
        task_id: str,
        result: str,
        run_id: str,
    ) -> None:
        task = await self._store.get_task(task_id)
        if task is None:
            return
        if task.status != TaskStatus.RUNNING:
            if task.status == TaskStatus.BLOCKED:
                await self._store.complete_run(
                    run_id,
                    TaskRunOutcome.BLOCKED,
                    error=task.blocked_reason or result,
                )
                logger.info("Task %s blocked during execution", task_id[:8])
            else:
                logger.warning(
                    "Task %s status changed to %s during execution, discarding success result",
                    task_id[:8],
                    task.status.value,
                )
                await self._store.complete_run(
                    run_id,
                    TaskRunOutcome.RECLAIMED,
                    error="Status changed during execution",
                )
            return

        if has_completion_intent(task.metadata):
            result = task.result or result

        if self._verifier:
            try:
                vr = await asyncio.wait_for(
                    self._verifier.verify(task, result),
                    timeout=60.0,
                )
            except TimeoutError:
                logger.warning("Task %s verification timed out", task_id[:8])
                await self._store.append_event(
                    task_id,
                    TaskEventKind.VERIFICATION_FAILED,
                    payload={"reason": "Verification timed out"},
                    run_id=run_id,
                )
                await self._handle_failure(task_id, "Verification timed out", run_id)
                return
            except Exception as exc:
                logger.warning("Task %s verification error: %s", task_id[:8], exc)
                await self._store.append_event(
                    task_id,
                    TaskEventKind.VERIFICATION_FAILED,
                    payload={"reason": f"Verification error: {exc}"},
                    run_id=run_id,
                )
                await self._handle_failure(
                    task_id,
                    f"Verification error: {exc}",
                    run_id,
                )
                return

            if not vr.passed:
                reason = vr.reason or "Completion verification failed"
                logger.warning(
                    "Task %s failed verification: %s",
                    task_id[:8],
                    reason,
                )
                await self._store.append_event(
                    task_id,
                    TaskEventKind.VERIFICATION_FAILED,
                    payload={"reason": reason, "error_logs": vr.error_logs or ""},
                    run_id=run_id,
                )
                self.emit("verification_failed", task)
                await self._handle_failure(task_id, reason, run_id)
                return

        usage = task.metadata.pop("last_token_usage", None) if isinstance(task.metadata, dict) else None
        cost = task.metadata.pop("last_cost_usd", None) if isinstance(task.metadata, dict) else None
        run_token_usage = usage if isinstance(usage, dict) else None
        run_cost_usd = float(cost) if isinstance(cost, (int, float)) else None

        if task.require_approval:
            task.status = TaskStatus.IN_REVIEW
            task.result = result
            task.consecutive_failures = 0
            task.block_cycle_count = 0
            task.error = ""
            task.progress_note = None
            task.metadata = clear_completion_intent(dict(task.metadata))
            await self._store.save_task(task)
            await self._store.complete_run(
                run_id,
                TaskRunOutcome.COMPLETED,
                summary=result,
                token_usage=run_token_usage,
                cost_usd=run_cost_usd,
            )
            await self._store.append_event(
                task_id,
                TaskEventKind.REVIEW_REQUESTED,
                run_id=run_id,
            )
            self.emit("task_review_requested", task)
            self.wake()
            logger.info("Task %s submitted for review", task_id[:8])
            return

        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = datetime.now(UTC)
        task.consecutive_failures = 0
        task.block_cycle_count = 0
        task.error = ""
        task.progress_note = None
        task.metadata = clear_completion_intent(dict(task.metadata))
        await self._store.save_task(task)
        await self._store.complete_run(
            run_id,
            TaskRunOutcome.COMPLETED,
            summary=result,
            token_usage=run_token_usage,
            cost_usd=run_cost_usd,
        )
        await self._store.append_event(
            task_id,
            TaskEventKind.COMPLETED,
            run_id=run_id,
        )
        self.emit("task_completed", task)
        await self._promote_dependents(task_id)
        self.wake()
        logger.info("Task %s completed", task_id[:8])

    async def _handle_blocked(
        self,
        task_id: str,
        reason: str,
        run_id: str,
        *,
        block_kind: BlockKind = BlockKind.HUMAN,
        scheduled_until: datetime | None = None,
        metadata_patch: dict[str, object] | None = None,
    ) -> None:
        """Handle an intentional task blockage (e.g., human review, wait state, budget limit pause).

        Persists the task status as BLOCKED, records a clean TaskRunOutcome.BLOCKED without
        incrementing consecutive_failures or triggering crash/retry degradation.
        """
        task = await self._store.get_task(task_id)
        if task is None:
            return

        task.status = TaskStatus.BLOCKED
        task.blocked_reason = reason
        task.block_kind = block_kind
        task.scheduled_until = scheduled_until
        task.progress_note = None
        task.error = ""
        # Do not increment consecutive_failures for intentional blocks
        task.consecutive_failures = 0

        if metadata_patch:
            task.metadata = {**task.metadata, **metadata_patch}

        usage = task.metadata.pop("last_token_usage", None) if isinstance(task.metadata, dict) else None
        cost = task.metadata.pop("last_cost_usd", None) if isinstance(task.metadata, dict) else None
        run_token_usage = usage if isinstance(usage, dict) else None
        run_cost_usd = float(cost) if isinstance(cost, (int, float)) else None

        await self._store.save_task(task)
        await self._store.complete_run(
            run_id,
            TaskRunOutcome.BLOCKED,
            error=reason,
            token_usage=run_token_usage,
            cost_usd=run_cost_usd,
        )
        await self._store.append_event(
            task_id,
            TaskEventKind.BLOCKED,
            payload={
                "reason": reason,
                "block_kind": block_kind.value,
                **({"scheduled_until": scheduled_until.isoformat()} if scheduled_until else {}),
            },
            run_id=run_id,
        )
        self.emit("task_blocked", task)
        self.wake()
        logger.info("Task %s entered intentional BLOCKED (%s): %s", task_id[:8], block_kind.value, reason[:80])

    # -- Dependency promotion --

    async def _promote_dependents(self, completed_task_id: str) -> None:
        """Promote BACKLOG children to READY when all their parents are terminal."""
        children_ids = await self._store.list_children(completed_task_id)
        for child_id in children_ids:
            child = await self._store.get_task(child_id)
            if child is None or child.status != TaskStatus.BACKLOG:
                continue
            if await self._store.are_dependencies_met(child_id):
                child.status = TaskStatus.READY
                await self._store.save_task(child)
                await self._store.append_event(
                    child_id,
                    TaskEventKind.PROMOTED,
                    payload={"trigger_task_id": completed_task_id},
                )
                self.emit("task_promoted", child)
                logger.info(
                    "Task %s promoted to READY (parent %s completed)",
                    child_id[:8],
                    completed_task_id[:8],
                )
