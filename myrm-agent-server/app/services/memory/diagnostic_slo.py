"""Memory diagnostics SLO rollup.

[INPUT]
app.services.memory.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本服务)

[OUTPUT]
build_diagnostic_slo: content-free diagnostic reliability rollup for Memory Doctor.

[POS]
单用户诊断可靠性汇总。只读取诊断事件元数据，不读取业务记忆内容。
"""

from __future__ import annotations

from app.schemas.memory.command_center import MemoryCommandDiagnosticSlo
from app.services.memory.operation_ledger import MemoryOperationLedgerService


async def build_diagnostic_slo(ledger: MemoryOperationLedgerService) -> MemoryCommandDiagnosticSlo:
    """Build a content-free SLO from recent diagnostic audit events."""

    events = await ledger.list_events(limit=100)
    diagnostic_events = [
        event for event in events if event.source == "memory_diagnostics" and event.target_id == "diagnostic_run"
    ][:20]
    if not diagnostic_events:
        return MemoryCommandDiagnosticSlo()

    failed_runs = 0
    durations: list[float] = []
    for event in diagnostic_events:
        metadata = event.metadata_json or {}
        status = str(metadata.get("diagnostic_status") or event.status)
        if status != "ready":
            failed_runs += 1
        duration = metadata.get("duration_ms")
        if isinstance(duration, (int, float)):
            durations.append(float(duration))

    window_runs = len(diagnostic_events)
    pass_rate = (window_runs - failed_runs) / window_runs if window_runs else 0.0
    average_duration_ms = sum(durations) / len(durations) if durations else 0.0
    if pass_rate >= 0.95:
        status = "ready"
    elif pass_rate >= 0.8:
        status = "warning"
    else:
        status = "critical"
    return MemoryCommandDiagnosticSlo(
        window_runs=window_runs,
        pass_rate=round(pass_rate, 4),
        failed_runs=failed_runs,
        average_duration_ms=round(average_duration_ms, 2),
        status=status,
    )
