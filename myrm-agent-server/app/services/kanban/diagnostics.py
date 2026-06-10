"""Kanban diagnostic engine factory and summary helpers.

[INPUT]
- diagnostic_rules (POS: Concrete diagnostic rule implementations.)
- myrm_agent_harness.toolkits.kanban.diagnostics (POS: Kanban diagnostic framework.)

[OUTPUT]
- create_diagnostic_engine, CARD_FAST_RULES, DiagnosticSummary, compute_diagnostics_summary

[POS]
Kanban diagnostic engine setup; rules live in diagnostic_rules.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.toolkits.kanban.diagnostics import (
    DiagnosticEngine,
    TaskDiagnostic,
    TaskDiagnosticSeverity,
)

from app.services.kanban.diagnostic_rules import (
    BlockUnblockCyclingRule,
    DeadDependencyRule,
    DiagnosticThresholds,
    RepeatedFailuresRule,
    StrandedInReadyRule,
    StrandedInTriageRule,
    StuckInBlockedRule,
    _error_snippet,
    _escalate_severity,
    _format_age,
    _hours_since,
)

__all__ = [
    "CARD_FAST_RULES",
    "BlockUnblockCyclingRule",
    "DeadDependencyRule",
    "DiagnosticSummary",
    "DiagnosticThresholds",
    "RepeatedFailuresRule",
    "StrandedInReadyRule",
    "StrandedInTriageRule",
    "StuckInBlockedRule",
    "_error_snippet",
    "_escalate_severity",
    "_format_age",
    "_hours_since",
    "compute_diagnostics_summary",
    "create_diagnostic_engine",
]

CARD_FAST_RULES: frozenset[str] = frozenset(
    {
        "stranded_in_ready",
        "repeated_failures",
        "stuck_in_blocked",
        "stranded_in_triage",
        "block_unblock_cycling",
    }
)


def create_diagnostic_engine(
    thresholds: DiagnosticThresholds | None = None,
) -> DiagnosticEngine:
    """Create a DiagnosticEngine with all 6 rules registered."""
    t = thresholds or DiagnosticThresholds()
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
    if not diagnostics:
        return DiagnosticSummary(count=0, max_severity=None)
    return DiagnosticSummary(
        count=len(diagnostics),
        max_severity=diagnostics[0].severity,
    )
