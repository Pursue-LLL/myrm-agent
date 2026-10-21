"""Kanban DAG plan revision business orchestration.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::PlanRevisionSpec, PlanRevisionOutcome
- myrm_agent_harness.toolkits.kanban.types::TaskStatus
- core.kanban.adapters::SqlAlchemyKanbanStore
- event_publisher::publish_kanban_event
- move_orchestrator::cancel_task_execution

[OUTPUT]
- revise_plan: Orchestrates atomic plan revision with running worker cancellation and downstream promotion.

[POS]
Orchestrates DAG plan revision across store transaction, worker cancellation, and downstream readiness.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import PlanRevisionOutcome, PlanRevisionSpec
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban.dependency_ops import promote_dependents
from app.services.kanban.event_publisher import publish_kanban_event

logger = logging.getLogger(__name__)

WakeDispatcher = Callable[[str], None]


async def revise_plan(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    spec: PlanRevisionSpec,
    *,
    wake_dispatcher: WakeDispatcher,
) -> PlanRevisionOutcome:
    """Execute atomic plan revision, cancelling removed/modified running workers and promoting children."""
    # 1. Pre-fetch running status of tasks targeted for remove/update to cancel workers if needed
    running_to_cancel: list[str] = []
    for item in spec.task_changes:
        if item.action in ("remove", "update") and item.task_id:
            t = await store.get_task(item.task_id)
            if t and t.status == TaskStatus.RUNNING:
                running_to_cancel.append(item.task_id)

    # 2. Execute atomic revision in store
    outcome = await store.revise_plan(spec)
    if not outcome.ok:
        logger.warning(
            "Plan revision rejected for board %s: %s",
            spec.board_id,
            outcome.reason,
        )
        return outcome

    # 3. Terminate running executions for cancelled/mutated tasks
    dispatcher = dispatchers.get(spec.board_id)
    for tid in running_to_cancel:
        if dispatcher:
            try:
                await dispatcher.cancel_execution(tid)
                logger.info("Cancelled running task execution %s due to plan revision", tid)
            except Exception as e:
                logger.warning("Failed to cancel execution for task %s: %s", tid, e)

    # 4. Promote dependents of any completed/archived tasks or newly added root tasks
    for tid in outcome.removed_task_ids:
        await promote_dependents(store, tid)

    # 5. Wake dispatcher to process any newly READY tasks
    if spec.board_id in dispatchers:
        wake_dispatcher(spec.board_id)

    # 6. Publish real-time SSE event for WebUI/Desktop
    publish_kanban_event(
        spec.board_id,
        spec.board_id,
        "plan_revised",
        title="Plan revised",
        detail=f"Added: {len(outcome.added_task_ids)}, Updated: {len(outcome.updated_task_ids)}, Removed: {len(outcome.removed_task_ids)}",
    )

    return outcome
