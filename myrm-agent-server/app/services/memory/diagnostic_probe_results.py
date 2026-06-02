"""Memory diagnostic probe result helpers.

[INPUT]
app.schemas.memory.command_center (POS: Memory Doctor response contracts)

[OUTPUT]
Probe result construction and diagnostic rollup helpers.

[POS]
单用户记忆诊断结果归一化工具。只处理状态与可视化契约，不读取业务记忆内容。
"""

from __future__ import annotations

from time import perf_counter
from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryOperationStatus

from app.schemas.memory.command_center import MemoryCommandDiagnosticProbeResult, MemoryCommandDoctorCheck

DiagnosticStatus = str
DiagnosticCategory = Literal["storage", "index", "embedding", "ledger", "deployment", "quality"]


def rollup_status(statuses: list[str]) -> DiagnosticStatus:
    if any(status == "critical" for status in statuses):
        return "critical"
    if any(status == "warning" for status in statuses):
        return "warning"
    if any(status == "missing" for status in statuses):
        return "missing"
    return "ready"


def operation_status(status: str) -> MemoryOperationStatus:
    if status == "critical":
        return MemoryOperationStatus.ERROR
    if status in {"warning", "missing"}:
        return MemoryOperationStatus.WARNING
    return MemoryOperationStatus.SUCCESS


def run_summary(status: str, failed_count: int, probe_count: int) -> str:
    if status == "ready":
        return f"All {probe_count} memory diagnostic probes passed."
    return f"{failed_count} of {probe_count} memory diagnostic probes need attention."


def missing_probe(
    *,
    probe_id: str,
    category: DiagnosticCategory,
    label: str,
    started: float,
    evidence: str,
    impact: str,
    next_action: str,
) -> MemoryCommandDiagnosticProbeResult:
    return MemoryCommandDiagnosticProbeResult(
        id=probe_id,
        category=category,
        label=label,
        status="missing",
        evidence=evidence,
        impact=impact,
        next_action=next_action,
        safe_to_retry=True,
        duration_ms=round((perf_counter() - started) * 1000, 2),
        repair_actions=["run_diagnostics"],
    )


def critical_probe(
    *,
    probe_id: str,
    category: DiagnosticCategory,
    label: str,
    started: float,
    evidence: str,
    impact: str,
    next_action: str,
    repair_actions: list[str],
) -> MemoryCommandDiagnosticProbeResult:
    return MemoryCommandDiagnosticProbeResult(
        id=probe_id,
        category=category,
        label=label,
        status="critical",
        evidence=evidence,
        impact=impact,
        next_action=next_action,
        safe_to_retry=True,
        duration_ms=round((perf_counter() - started) * 1000, 2),
        repair_actions=repair_actions,
    )


def doctor_check_to_probe(
    check: MemoryCommandDoctorCheck,
    *,
    duration_ms: float,
) -> MemoryCommandDiagnosticProbeResult:
    return MemoryCommandDiagnosticProbeResult(
        id=check.id,
        category=check.category,
        label=check.label,
        status=check.status,
        evidence=check.evidence,
        impact=check.impact,
        next_action=check.next_action,
        can_auto_fix=check.can_auto_fix,
        safe_to_retry=check.safe_to_retry,
        docs_ref=check.docs_ref,
        duration_ms=duration_ms,
        repair_actions=check.repair_actions,
        repair_plans=check.repair_plans,
    )
