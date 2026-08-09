"""Kanban cycling / review-stall diagnostic rules.

[INPUT]
- diagnostic_rules (POS: Shared thresholds, severity helpers and time formatting.)
- myrm_agent_harness.toolkits.kanban.diagnostics (POS: Kanban diagnostic framework.)
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)

[OUTPUT]
- BlockUnblockCyclingRule, StrandedInReviewRule

[POS]
Rules for block→unblock cycling and tasks stranded in IN_REVIEW.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.kanban.diagnostics import (
    DiagnosticAction,
    DiagnosticContext,
    TaskDiagnostic,
)
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.services.kanban.diagnostic_rules import (
    _DEFAULT_THRESHOLDS,
    DiagnosticThresholds,
    _escalate_severity,
    _format_age,
    _hours_since,
)


class BlockUnblockCyclingRule:
    def __init__(self, thresholds: DiagnosticThresholds = _DEFAULT_THRESHOLDS) -> None:
        self._threshold = thresholds.block_cycle_threshold

    @property
    def rule_id(self) -> str:
        return "block_unblock_cycling"

    def evaluate(
        self,
        task: KanbanTask,
        *,
        context: DiagnosticContext | None = None,
    ) -> list[TaskDiagnostic]:
        cycles = task.block_cycle_count
        if cycles < self._threshold:
            return []
        severity = _escalate_severity(cycles, self._threshold)
        reason_snippet = task.blocked_reason[:100] if task.blocked_reason else ""
        title = (
            f"Block→unblock cycled {cycles}x: {reason_snippet}"
            if reason_snippet
            else f"Block→unblock cycled {cycles}x"
        )
        return [
            TaskDiagnostic(
                rule_id=self.rule_id,
                severity=severity,
                title=title,
                detail=(
                    f"This task has been blocked {cycles} times by the worker agent. "
                    f"Unblocking alone is not resolving the root cause. "
                    f"Review the block reasons and consider a different intervention: "
                    f"update the task description, reassign, or archive."
                ),
                actions=(
                    DiagnosticAction(
                        kind="comment",
                        label="Add comment",
                        payload={},
                        suggested=True,
                    ),
                    DiagnosticAction(
                        kind="archive",
                        label="Archive",
                        payload={"target_status": "archived"},
                    ),
                ),
            )
        ]


class StrandedInReviewRule:
    """Flags IN_REVIEW tasks that have awaited human approval for too long."""

    def __init__(self, thresholds: DiagnosticThresholds = _DEFAULT_THRESHOLDS) -> None:
        self._hours = thresholds.stranded_in_review_hours

    @property
    def rule_id(self) -> str:
        return "stranded_in_review"

    def evaluate(
        self,
        task: KanbanTask,
        *,
        context: DiagnosticContext | None = None,
    ) -> list[TaskDiagnostic]:
        if task.status != TaskStatus.IN_REVIEW:
            return []
        hours_in_review = _hours_since(task.updated_at)
        if hours_in_review < self._hours:
            return []
        severity = _escalate_severity(hours_in_review, self._hours)
        return [
            TaskDiagnostic(
                rule_id=self.rule_id,
                severity=severity,
                title=f"Awaiting approval for {_format_age(hours_in_review)}",
                detail=(
                    f"This task has awaited human approval for {hours_in_review:.0f}h. "
                    "Review its result and approve it, or reject it with feedback to rework."
                ),
            )
        ]
