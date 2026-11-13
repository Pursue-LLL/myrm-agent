"""Kanban run outcomes — what a finished agent run means for its task.

[INPUT]
- myrm_agent_harness.toolkits.kanban.types::BlockKind, TaskExecutionResult, TaskStatus, has_completion_intent (POS: Kanban domain types and the completion-intent gate.)
- myrm_agent_harness.agent.goals.types::GoalStatus (POS: Goal lifecycle states mapped to task outcomes.)

[OUTPUT]
- PROTOCOL_VIOLATION_MSG: Failure text of a run that ended without calling ``kanban_complete``.
- APPROVAL_NEEDED_BLOCK_REASON: Written to a task whose run stopped on an approval nobody can give while it runs.
- map_goal_outcome: Maps a goal-mode run's terminal goal status to the kanban result and persists it.
- resolve_run_outcome: Re-reads the task after a run and applies the completion gate and the approval stop.

[POS]
Interprets the end of one agent run: the goal-mode mapping and the completion gate that decides whether
the task succeeded, failed or is blocked. Kept apart from ``KanbanTaskRunner`` so the runner owns scheduling and
locking while this module owns the verdict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    TaskExecutionResult,
    TaskStatus,
    has_completion_intent,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.api import KanbanStore
    from myrm_agent_harness.toolkits.kanban.types import KanbanTask

PROTOCOL_VIOLATION_MSG = "Protocol violation: agent finished without calling kanban_complete(summary=...)"
APPROVAL_NEEDED_BLOCK_REASON = (
    "An action needs approval, but tasks run unattended; allow it in the security policy, then continue"
)


async def map_goal_outcome(
    store: KanbanStore,
    task: KanbanTask,
    goal_provider: GoalProvider,
    agent_result: tuple[bool, str],
) -> tuple[bool, str] | TaskExecutionResult:
    """Map Goal terminal status to Kanban result with SSOT persistence."""
    from myrm_agent_harness.agent.goals.types import GoalStatus

    session_id = f"kanban:{task.task_id}"
    goal = await goal_provider.get_latest_goal(session_id)
    if not goal:
        return agent_result

    acceptance_results = goal.metadata.get("acceptance_results")
    fresh = await store.get_task(task.task_id)

    meta_patch: dict[str, object] = {}
    if acceptance_results:
        meta_patch["acceptance_results"] = acceptance_results

    if goal.status == GoalStatus.COMPLETE:
        if fresh is not None:
            updated_meta = dict(fresh.metadata)
            if acceptance_results:
                updated_meta["acceptance_results"] = acceptance_results
            fresh.metadata = updated_meta
            await store.save_task(fresh)

        if fresh is not None and has_completion_intent(fresh.metadata):
            turns_info = f" ({goal.turns_used} turns)"
            summary = fresh.result or agent_result[1] or "Goal completed"
            return TaskExecutionResult.success(summary + turns_info, metadata_patch=meta_patch)
        return TaskExecutionResult.failure(PROTOCOL_VIOLATION_MSG, metadata_patch=meta_patch)

    if goal.status in (
        GoalStatus.PAUSED,
        GoalStatus.NEEDS_HUMAN_REVIEW,
        GoalStatus.WAIT,
    ):
        pause_reason = str(goal.metadata.get("pause_reason") or goal.metadata.get("wait_reason") or "needs review")
        block_kind = BlockKind.EXTERNAL if goal.status == GoalStatus.WAIT else BlockKind.HUMAN
        if fresh is not None:
            fresh.status = TaskStatus.BLOCKED
            fresh.blocked_reason = pause_reason
            fresh.block_kind = block_kind
            updated_meta = dict(fresh.metadata)
            if acceptance_results:
                updated_meta["acceptance_results"] = acceptance_results
            fresh.metadata = updated_meta
            await store.save_task(fresh)
        return TaskExecutionResult.blocked(
            pause_reason,
            block_kind=block_kind,
            metadata_patch=meta_patch,
        )

    if goal.status == GoalStatus.BUDGET_LIMITED:
        pause_reason = f"Budget exhausted after {goal.turns_used} turns"
        if fresh is not None:
            fresh.status = TaskStatus.BLOCKED
            fresh.blocked_reason = pause_reason
            fresh.block_kind = BlockKind.HUMAN
            updated_meta = dict(fresh.metadata)
            if acceptance_results:
                updated_meta["acceptance_results"] = acceptance_results
            fresh.metadata = updated_meta
            await store.save_task(fresh)
        return TaskExecutionResult.blocked(
            pause_reason,
            block_kind=BlockKind.HUMAN,
            metadata_patch=meta_patch,
        )

    return agent_result


async def resolve_run_outcome(
    store: KanbanStore,
    task_id: str,
    agent_result: tuple[bool, str] | TaskExecutionResult,
    *,
    approval_needed: bool = False,
) -> tuple[bool, str] | TaskExecutionResult:
    """Re-read task state after agent execution to enforce completion gate.

    ``approval_needed``: the stream ended on an approval request. A task that blocked itself or completed keeps that
    verdict; otherwise the run is blocked for the user, since a retry would stop at the same request.
    """
    if isinstance(agent_result, TaskExecutionResult):
        return agent_result

    fresh = await store.get_task(task_id)
    if fresh is None:
        return False, "Task not found after execution"

    if fresh.status == TaskStatus.BLOCKED:
        return TaskExecutionResult.blocked(
            fresh.blocked_reason or "Task blocked by agent",
            block_kind=fresh.block_kind or BlockKind.HUMAN,
            scheduled_until=fresh.scheduled_until,
        )

    if has_completion_intent(fresh.metadata):
        summary = fresh.result or agent_result[1]
        if not summary.strip():
            return False, "Protocol violation: kanban_complete summary is empty"
        return True, summary

    if approval_needed:
        return TaskExecutionResult.blocked(APPROVAL_NEEDED_BLOCK_REASON, block_kind=BlockKind.HUMAN)

    if agent_result[0]:
        return False, PROTOCOL_VIOLATION_MSG

    return agent_result
