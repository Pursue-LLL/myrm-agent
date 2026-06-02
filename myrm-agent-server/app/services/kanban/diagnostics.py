"""Kanban diagnostic rules and engine setup.

Implements 6 concrete diagnostic rules:
1. stranded_in_ready: Task in READY for too long without being picked up.
2. repeated_failures: Task has high consecutive failure count.
3. stuck_in_blocked: Task in BLOCKED for too long without resolution.
4. dead_dependency: Task in BACKLOG whose ALL parents are in non-completed terminal states.
5. stranded_in_triage: Task in TRIAGE for too long without being specified.
6. block_unblock_cycling: Task repeatedly blocked→unblocked without root cause resolution.

[INPUT]
- myrm_agent_harness.toolkits.kanban.diagnostics (POS: Kanban diagnostic framework.)
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)

[OUTPUT]
- StrandedInReadyRule, RepeatedFailuresRule, StuckInBlockedRule, DeadDependencyRule,
  StrandedInTriageRule, BlockUnblockCyclingRule
- CARD_FAST_RULES: frozenset of rule_ids safe for O(1) card-level evaluation
- create_diagnostic_engine: Factory that builds engine with all rules registered
- compute_diagnostics_summary: Summarize diagnostics for card badges

[POS]
Kanban diagnostic rules and engine setup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.kanban.diagnostics import (
    DiagnosticAction,
    DiagnosticContext,
    DiagnosticEngine,
    TaskDiagnostic,
    TaskDiagnosticSeverity,
)
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus


@dataclass(frozen=True, slots=True)
class DiagnosticThresholds:
    """Configurable thresholds for diagnostic rules."""

    stranded_ready_hours: float = 24.0
    stuck_blocked_hours: float = 48.0
    repeated_failure_threshold: int = 3
    stranded_triage_hours: float = 8.0
    block_cycle_threshold: int = 3


_DEFAULT_THRESHOLDS = DiagnosticThresholds()

_MAX_ERROR_SNIPPET = 200


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------


def _escalate_severity(
    value: float, threshold: float,
) -> TaskDiagnosticSeverity:
    """Escalate severity based on how far past the threshold we are.

    - 1x–2x threshold → warning
    - 2x–7x threshold → error
    - ≥7x threshold → critical
    """
    if value >= threshold * 7:
        return TaskDiagnosticSeverity.CRITICAL
    if value >= threshold * 2:
        return TaskDiagnosticSeverity.ERROR
    return TaskDiagnosticSeverity.WARNING


def _format_age(hours: float) -> str:
    """Format an age in hours into a human-friendly string."""
    if hours >= 24:
        days = hours / 24
        return f"{days:.0f}d" if days >= 2 else f"{hours:.0f}h"
    return f"{hours:.0f}h"


def _error_snippet(error: str) -> str:
    """Truncate error text for display in diagnostics."""
    text = error.strip()
    if not text:
        return ""
    first_line = text.splitlines()[0][:_MAX_ERROR_SNIPPET]
    if len(text) > _MAX_ERROR_SNIPPET:
        first_line += "…"
    return first_line


# ---------------------------------------------------------------------------
# Rule 1: stranded_in_ready
# ---------------------------------------------------------------------------


class StrandedInReadyRule:
    """Detects tasks sitting in READY status for too long.

    Severity escalates with age via _escalate_severity.
    """

    def __init__(self, thresholds: DiagnosticThresholds = _DEFAULT_THRESHOLDS) -> None:
        self._hours = thresholds.stranded_ready_hours

    @property
    def rule_id(self) -> str:
        return "stranded_in_ready"

    def evaluate(
        self,
        task: KanbanTask,
        *,
        context: DiagnosticContext | None = None,
    ) -> list[TaskDiagnostic]:
        if task.status != TaskStatus.READY:
            return []
        hours_in_ready = _hours_since(task.updated_at)
        if hours_in_ready < self._hours:
            return []
        severity = _escalate_severity(hours_in_ready, self._hours)
        return [
            TaskDiagnostic(
                rule_id=self.rule_id,
                severity=severity,
                title=f"Ready for {_format_age(hours_in_ready)} without dispatcher",
                detail=(
                    f"This task has been in READY for {hours_in_ready:.0f}h "
                    f"without being picked up. Check that the assignee is correct "
                    f"and a dispatcher is running."
                ),
                actions=(
                    DiagnosticAction(
                        kind="archive",
                        label="Archive",
                        payload={"target_status": "archived"},
                    ),
                ),
            )
        ]


# ---------------------------------------------------------------------------
# Rule 2: repeated_failures
# ---------------------------------------------------------------------------


class RepeatedFailuresRule:
    """Detects tasks with high consecutive failure counts.

    Severity: error when ≥threshold, critical when ≥threshold*2 or auto-blocked.
    """

    def __init__(self, thresholds: DiagnosticThresholds = _DEFAULT_THRESHOLDS) -> None:
        self._threshold = thresholds.repeated_failure_threshold

    @property
    def rule_id(self) -> str:
        return "repeated_failures"

    def evaluate(
        self,
        task: KanbanTask,
        *,
        context: DiagnosticContext | None = None,
    ) -> list[TaskDiagnostic]:
        failures = task.consecutive_failures
        if failures < self._threshold:
            return []
        severity = (
            TaskDiagnosticSeverity.CRITICAL
            if task.status == TaskStatus.BLOCKED or failures >= self._threshold * 2
            else TaskDiagnosticSeverity.ERROR
        )

        err = _error_snippet(task.error)
        title = f"Failed {failures}x: {err}" if err else f"Failed {failures}x consecutively"

        detail_parts = [
            f"This task has failed {failures} times consecutively.",
        ]
        if task.status == TaskStatus.BLOCKED:
            detail_parts.append("Auto-blocked by dispatcher.")
        if err:
            detail_parts.append(f"Last error: {err}")
        detail_parts.append(
            "Consider reviewing the task description or archiving it."
        )

        actions: list[DiagnosticAction] = []
        if task.status == TaskStatus.BLOCKED:
            actions.append(
                DiagnosticAction(
                    kind="move_to_ready",
                    label="Retry (move to Ready)",
                    payload={"target_status": "ready"},
                    suggested=True,
                )
            )
        actions.append(
            DiagnosticAction(
                kind="archive",
                label="Archive",
                payload={"target_status": "archived"},
            )
        )
        return [
            TaskDiagnostic(
                rule_id=self.rule_id,
                severity=severity,
                title=title,
                detail=" ".join(detail_parts),
                actions=tuple(actions),
            )
        ]


# ---------------------------------------------------------------------------
# Rule 3: stuck_in_blocked
# ---------------------------------------------------------------------------


class StuckInBlockedRule:
    """Detects tasks stuck in BLOCKED status for too long.

    Severity escalates with age via _escalate_severity.
    """

    def __init__(self, thresholds: DiagnosticThresholds = _DEFAULT_THRESHOLDS) -> None:
        self._hours = thresholds.stuck_blocked_hours

    @property
    def rule_id(self) -> str:
        return "stuck_in_blocked"

    def evaluate(
        self,
        task: KanbanTask,
        *,
        context: DiagnosticContext | None = None,
    ) -> list[TaskDiagnostic]:
        if task.status != TaskStatus.BLOCKED:
            return []
        hours_blocked = _hours_since(task.updated_at)
        if hours_blocked < self._hours:
            return []
        severity = _escalate_severity(hours_blocked, self._hours)
        reason_snippet = task.blocked_reason[:100] if task.blocked_reason else ""
        title = (
            f"Blocked for {_format_age(hours_blocked)}: {reason_snippet}"
            if reason_snippet
            else f"Blocked for {_format_age(hours_blocked)}"
        )
        return [
            TaskDiagnostic(
                rule_id=self.rule_id,
                severity=severity,
                title=title,
                detail=(
                    f"This task has been BLOCKED for {hours_blocked:.0f}h. "
                    f"Reason: {task.blocked_reason or 'not specified'}. "
                    f"Add a comment to explain the situation, then unblock or archive."
                ),
                actions=(
                    DiagnosticAction(
                        kind="comment",
                        label="Add comment",
                        payload={},
                        suggested=True,
                    ),
                    DiagnosticAction(
                        kind="move_to_ready",
                        label="Unblock (move to Ready)",
                        payload={"target_status": "ready"},
                    ),
                    DiagnosticAction(
                        kind="archive",
                        label="Archive",
                        payload={"target_status": "archived"},
                    ),
                ),
            )
        ]


# ---------------------------------------------------------------------------
# Rule 4: dead_dependency
# ---------------------------------------------------------------------------


class DeadDependencyRule:
    """Detects BACKLOG tasks whose ALL parents are in non-completed terminal states.

    Requires DiagnosticContext with parent status information.
    """

    @property
    def rule_id(self) -> str:
        return "dead_dependency"

    def evaluate(
        self,
        task: KanbanTask,
        *,
        context: DiagnosticContext | None = None,
    ) -> list[TaskDiagnostic]:
        if task.status != TaskStatus.BACKLOG:
            return []
        if context is None or not context.parent_task_ids:
            return []

        all_parents_dead = all(
            context.parent_statuses.get(pid) in ("failed", "archived")
            for pid in context.parent_task_ids
        )
        if not all_parents_dead:
            return []

        n = len(context.parent_task_ids)
        return [
            TaskDiagnostic(
                rule_id=self.rule_id,
                severity=TaskDiagnosticSeverity.ERROR,
                title=f"All {n} parent{'s' if n > 1 else ''} dead",
                detail=(
                    f"All {n} parent tasks are in failed/archived status. "
                    f"This task will never be promoted to READY."
                ),
                actions=(
                    DiagnosticAction(
                        kind="archive",
                        label="Archive",
                        payload={"target_status": "archived"},
                        suggested=True,
                    ),
                ),
            )
        ]


# ---------------------------------------------------------------------------
# Rule 5: stranded_in_triage
# ---------------------------------------------------------------------------


class StrandedInTriageRule:
    """Detects tasks sitting in TRIAGE status too long without being specified.

    Triage is the inbox for rough ideas. Sitting there indefinitely either
    means the user forgot it or the Specifier is silently unavailable.
    Severity escalates with age via ``_escalate_severity``.
    """

    def __init__(self, thresholds: DiagnosticThresholds = _DEFAULT_THRESHOLDS) -> None:
        self._hours = thresholds.stranded_triage_hours

    @property
    def rule_id(self) -> str:
        return "stranded_in_triage"

    def evaluate(
        self,
        task: KanbanTask,
        *,
        context: DiagnosticContext | None = None,
    ) -> list[TaskDiagnostic]:
        if task.status != TaskStatus.TRIAGE:
            return []
        hours_in_triage = _hours_since(task.updated_at)
        if hours_in_triage < self._hours:
            return []
        severity = _escalate_severity(hours_in_triage, self._hours)
        return [
            TaskDiagnostic(
                rule_id=self.rule_id,
                severity=severity,
                title=f"Idle in Triage for {_format_age(hours_in_triage)}",
                detail=(
                    f"This task has been waiting in Triage for {hours_in_triage:.0f}h "
                    f"without being specified. Run Specify to convert the rough idea "
                    f"into an actionable spec, or archive it if no longer relevant."
                ),
                actions=(
                    DiagnosticAction(
                        kind="specify",
                        label="Specify with LLM",
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


# ---------------------------------------------------------------------------
# Rule 6: block_unblock_cycling
# ---------------------------------------------------------------------------


class BlockUnblockCyclingRule:
    """Detects tasks that cycle through blocked→unblocked repeatedly.

    Complements StuckInBlockedRule: that rule uses ``_hours_since(updated_at)``
    which resets on every unblock, making it blind to rapid cycling.  This rule
    uses the ``block_cycle_count`` counter incremented each time an agent calls
    ``kanban_block``, catching the pattern where unblock does not address the
    root cause and the worker keeps hitting the same wall.

    Severity escalates with cycle count via ``_escalate_severity``.
    """

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


# ---------------------------------------------------------------------------
# Engine factory & helpers
# ---------------------------------------------------------------------------

CARD_FAST_RULES: frozenset[str] = frozenset({
    "stranded_in_ready",
    "repeated_failures",
    "stuck_in_blocked",
    "stranded_in_triage",
    "block_unblock_cycling",
})


def create_diagnostic_engine(
    thresholds: DiagnosticThresholds | None = None,
) -> DiagnosticEngine:
    """Create a DiagnosticEngine with all 6 rules registered."""
    t = thresholds or _DEFAULT_THRESHOLDS
    engine = DiagnosticEngine()
    engine.register(StrandedInReadyRule(t))
    engine.register(RepeatedFailuresRule(t))
    engine.register(StuckInBlockedRule(t))
    engine.register(DeadDependencyRule())
    engine.register(StrandedInTriageRule(t))
    engine.register(BlockUnblockCyclingRule(t))
    return engine


@dataclass(frozen=True, slots=True)
class DiagnosticSummary:
    """Lightweight summary for card-level badges."""

    count: int
    max_severity: TaskDiagnosticSeverity | None


def compute_diagnostics_summary(
    diagnostics: list[TaskDiagnostic],
) -> DiagnosticSummary:
    """Summarize a list of diagnostics into count + highest severity."""
    if not diagnostics:
        return DiagnosticSummary(count=0, max_severity=None)
    return DiagnosticSummary(
        count=len(diagnostics),
        max_severity=diagnostics[0].severity,
    )


def _hours_since(dt: datetime) -> float:
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (now - dt).total_seconds() / 3600
