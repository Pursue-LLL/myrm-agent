"""Dual-track compliance audit trail aggregation and export for security services.

[INPUT]
- app.schemas.security.dashboard (POS: Dual-track audit DTO schemas)
- myrm_agent_harness.observability.audit_trail (POS: Harness compliance audit collector & exporter)

[OUTPUT]
- get_default_audit_collector
- fetch_dual_track_audit_entries
- fetch_dual_track_audit_stats
- export_dual_track_compliance_dossier

[POS]
安全仪表盘双轨意图与合规审计日志聚合及导出。
"""

from __future__ import annotations

from typing import Literal

from fastapi.responses import Response

from app.schemas.security.dashboard import (
    DualTrackAuditEntryItem,
    DualTrackAuditStatsResponse,
    RuleTriggerHitItem,
)
from myrm_agent_harness.observability.audit_trail import (
    ComplianceOutcome,
    ComplianceTrailExporter,
    DualTrackAuditCollector,
)

_DEFAULT_COLLECTOR = DualTrackAuditCollector(max_entries=5000)


def get_default_audit_collector() -> DualTrackAuditCollector:
    return _DEFAULT_COLLECTOR


def fetch_dual_track_audit_entries(
    *,
    session_id: str | None = None,
    agent_id: str | None = None,
    outcome: str | None = None,
    limit: int = 100,
) -> list[DualTrackAuditEntryItem]:
    """Retrieve filtered dual-track audit trail entries."""
    parsed_outcome: ComplianceOutcome | None = None
    if outcome:
        try:
            parsed_outcome = ComplianceOutcome(outcome.upper())
        except ValueError:
            pass

    entries = _DEFAULT_COLLECTOR.list_entries(
        session_id=session_id,
        agent_id=agent_id,
        outcome=parsed_outcome,
        limit=limit,
    )

    return [
        DualTrackAuditEntryItem(
            entry_id=e.entry_id,
            session_id=e.session_id,
            agent_id=e.agent_id,
            tool_name=e.tool_name,
            intent_summary=e.intent_summary,
            raw_intent_args=dict(e.raw_intent_args),
            rule_name=e.rule_name,
            state=str(e.state),
            outcome=str(e.outcome),
            is_human_take_the_wheel=e.is_human_take_the_wheel,
            created_at=e.created_at.isoformat(),
            completed_at=e.completed_at.isoformat() if e.completed_at else None,
            latency_ms=e.latency_ms,
            output_length=e.output_length,
            error_message=e.error_message,
        )
        for e in entries
    ]


def fetch_dual_track_audit_stats(
    *,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> DualTrackAuditStatsResponse:
    """Compute aggregated compliance metrics and rule trigger distributions."""
    stats = _DEFAULT_COLLECTOR.get_summary_stats(session_id=session_id, agent_id=agent_id)
    return DualTrackAuditStatsResponse(
        total_entries=stats.total_entries,
        permitted_count=stats.permitted_count,
        refused_count=stats.refused_count,
        failed_count=stats.failed_count,
        human_take_the_wheel_count=stats.human_take_the_wheel_count,
        compliance_rate=stats.compliance_rate,
        avg_latency_ms=stats.avg_latency_ms,
        top_rules_triggered=[
            RuleTriggerHitItem(
                rule_name=r.rule_name,
                trigger_count=r.trigger_count,
                refused_count=r.refused_count,
                permitted_count=r.permitted_count,
                failed_count=r.failed_count,
                refusal_rate=r.refusal_rate,
                sample_targets=list(r.sample_targets),
            )
            for r in stats.top_rules_triggered
        ],
    )


def export_dual_track_compliance_dossier(
    *,
    export_format: Literal["json", "csv", "markdown"] = "json",
    session_id: str | None = None,
    agent_id: str | None = None,
    time_window_hours: int = 24,
) -> Response:
    """Generate and return sealed zero-leakage compliance audit export."""
    report = ComplianceTrailExporter.generate_report(
        _DEFAULT_COLLECTOR,
        session_id=session_id,
        agent_id=agent_id,
        time_window_hours=time_window_hours,
    )

    if export_format == "csv":
        content = ComplianceTrailExporter.export_csv(report)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=compliance_trail_{report.report_id}.csv"},
        )
    if export_format == "markdown":
        content = ComplianceTrailExporter.export_markdown(report)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=compliance_dossier_{report.report_id}.md"},
        )

    content = ComplianceTrailExporter.export_json(report)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=compliance_report_{report.report_id}.json"},
    )
