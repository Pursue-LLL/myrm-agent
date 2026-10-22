"""
[INPUT]: Session IDs, tool call metrics, retry traces, and role view selections.
[OUTPUT]: Quantified SessionSavingsAudit war reports, 7-signal pattern detections, and RoleEngineeringInsightReport evaluations.
[POS]: myrm-agent/myrm-agent-server/app/api/system/context_savings_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.context_optimization import (
    ContextOptimizationSavingsAuditor,
    EngineeringSignalAnalyzer,
    EngineeringSignalItem,
    EngineeringSignalPattern,
    RoleEngineeringInsightReport,
    RoleInsightView,
    SessionSavingsAudit,
    ToolSavingsRecord,
    ToolSavingsSummary,
)

router = APIRouter(tags=["context-savings"])

_auditor = ContextOptimizationSavingsAuditor()
_analyzer = EngineeringSignalAnalyzer()


# --- Pydantic Schemas ---

class RecordToolSavingsRequest(BaseModel):
    session_id: str
    tool_name: str
    original_bytes: int = Field(ge=0)
    optimized_bytes: int = Field(ge=0)
    cache_hit: bool = False
    explicit_original_tokens: Optional[int] = Field(default=None, ge=0)
    explicit_optimized_tokens: Optional[int] = Field(default=None, ge=0)


class ToolSavingsResponse(BaseModel):
    session_id: str
    tool_name: str
    original_tokens: int
    optimized_tokens: int
    saved_tokens: int
    savings_rate_pct: float
    cost_saved_usd: float
    cost_saved_cny: float
    cache_hit: bool
    recorded_at: str


class ToolSavingsSummaryResponse(BaseModel):
    tool_name: str
    total_calls: int
    total_original_tokens: int
    total_optimized_tokens: int
    total_saved_tokens: int
    average_savings_rate_pct: float
    total_cost_saved_usd: float
    total_cost_saved_cny: float
    cache_hit_rate_pct: float


class SessionSavingsAuditResponse(BaseModel):
    session_id: str
    total_tool_calls: int
    total_original_tokens: int
    total_optimized_tokens: int
    total_saved_tokens: int
    overall_savings_rate_pct: float
    total_cost_saved_usd: float
    total_cost_saved_cny: float
    tool_breakdown: List[ToolSavingsSummaryResponse]
    summary_headline: str


class ScanSessionSignalsRequest(BaseModel):
    session_id: str
    tool_retry_counts: Dict[str, int] = Field(default_factory=dict)
    tool_latencies_ms: Dict[str, float] = Field(default_factory=dict)


class EngineeringSignalResponse(BaseModel):
    signal_pattern: str
    severity: str
    target_entity: str
    detected_metric_value: float
    metric_threshold: float
    root_cause_explanation: str
    actionable_remediation: str


class RoleInsightReportResponse(BaseModel):
    role: str
    evaluated_sessions_count: int
    total_saved_tokens_aggregate: int
    total_cost_saved_usd_aggregate: float
    top_efficiency_tools: List[str]
    identified_engineering_signals: List[EngineeringSignalResponse]
    primary_bottleneck_summary: str


# --- Helper Converters ---

def _convert_tool_summary(s: ToolSavingsSummary) -> ToolSavingsSummaryResponse:
    return ToolSavingsSummaryResponse(
        tool_name=s.tool_name,
        total_calls=s.total_calls,
        total_original_tokens=s.total_original_tokens,
        total_optimized_tokens=s.total_optimized_tokens,
        total_saved_tokens=s.total_saved_tokens,
        average_savings_rate_pct=s.average_savings_rate_pct,
        total_cost_saved_usd=s.total_cost_saved_usd,
        total_cost_saved_cny=s.total_cost_saved_cny,
        cache_hit_rate_pct=s.cache_hit_rate_pct,
    )


def _convert_audit(a: SessionSavingsAudit) -> SessionSavingsAuditResponse:
    return SessionSavingsAuditResponse(
        session_id=a.session_id,
        total_tool_calls=a.total_tool_calls,
        total_original_tokens=a.total_original_tokens,
        total_optimized_tokens=a.total_optimized_tokens,
        total_saved_tokens=a.total_saved_tokens,
        overall_savings_rate_pct=a.overall_savings_rate_pct,
        total_cost_saved_usd=a.total_cost_saved_usd,
        total_cost_saved_cny=a.total_cost_saved_cny,
        tool_breakdown=[_convert_tool_summary(t) for t in a.tool_breakdown],
        summary_headline=a.summary_headline,
    )


def _convert_signal(sig: EngineeringSignalItem) -> EngineeringSignalResponse:
    return EngineeringSignalResponse(
        signal_pattern=sig.signal_pattern.value,
        severity=sig.severity,
        target_entity=sig.target_entity,
        detected_metric_value=sig.detected_metric_value,
        metric_threshold=sig.metric_threshold,
        root_cause_explanation=sig.root_cause_explanation,
        actionable_remediation=sig.actionable_remediation,
    )


# --- HTTP Endpoints ---

@router.post(
    "/context-savings/record-tool",
    response_model=ToolSavingsResponse,
    summary="登记单次工具输出截断与上下文拦截节流指标",
)
def record_tool_savings(payload: RecordToolSavingsRequest) -> ToolSavingsResponse:
    rec = _auditor.record_tool_call(
        session_id=payload.session_id,
        tool_name=payload.tool_name,
        original_bytes=payload.original_bytes,
        optimized_bytes=payload.optimized_bytes,
        cache_hit=payload.cache_hit,
        explicit_original_tokens=payload.explicit_original_tokens,
        explicit_optimized_tokens=payload.explicit_optimized_tokens,
    )
    return ToolSavingsResponse(
        session_id=rec.session_id,
        tool_name=rec.tool_name,
        original_tokens=rec.original_tokens,
        optimized_tokens=rec.optimized_tokens,
        saved_tokens=rec.saved_tokens,
        savings_rate_pct=rec.savings_rate_pct,
        cost_saved_usd=rec.cost_saved_usd,
        cost_saved_cny=rec.cost_saved_cny,
        cache_hit=rec.cache_hit,
        recorded_at=rec.recorded_at,
    )


@router.get(
    "/context-savings/session/{session_id}",
    response_model=SessionSavingsAuditResponse,
    summary="获取指定会话上下文拦截节流战报 (节省 Token 数、节省率与财务价值)",
)
def get_session_audit(session_id: str) -> SessionSavingsAuditResponse:
    audit = _auditor.get_session_audit(session_id)
    return _convert_audit(audit)


@router.post(
    "/context-savings/analyze-session",
    response_model=List[EngineeringSignalResponse],
    summary="扫描会话执行事件，挖掘 7 维工程障碍模式信号 (输出膨胀/重试死循环/阻塞I/O/缓存饥渴)",
)
def analyze_session_signals(payload: ScanSessionSignalsRequest) -> List[EngineeringSignalResponse]:
    audit = _auditor.get_session_audit(payload.session_id)
    # Pull raw records for cache hit assessment
    with _auditor._lock:
        records = list(_auditor._records.get(payload.session_id, []))

    signals = _analyzer.analyze_session_signals(
        audit=audit,
        tool_records=records,
        tool_retry_counts=payload.tool_retry_counts,
        tool_latencies_ms=payload.tool_latencies_ms,
    )
    return [_convert_signal(s) for s in signals]


@router.get(
    "/context-savings/engineering-insights",
    response_model=RoleInsightReportResponse,
    summary="按研发决策角色 (CTO/EM/FinOps/DevOps) 聚合工程效能洞察与阻塞瓶颈大盘",
)
def get_engineering_insights(
    role: str = Query(default="CTO", description="目标角色：CTO | EM | FINOPS | DEVOPS"),
) -> RoleInsightReportResponse:
    role_enum_map = {
        "CTO": RoleInsightView.CTO,
        "EM": RoleInsightView.EM,
        "FINOPS": RoleInsightView.FINOPS,
        "DEVOPS": RoleInsightView.DEVOPS,
    }
    role_enum = role_enum_map.get(role.upper(), RoleInsightView.CTO)

    all_sessions = _auditor.list_all_sessions()
    audits = [_auditor.get_session_audit(sid) for sid in all_sessions]

    # Collect signals across all sessions
    all_signals: List[EngineeringSignalItem] = []
    for sid in all_sessions:
        audit = _auditor.get_session_audit(sid)
        with _auditor._lock:
            records = list(_auditor._records.get(sid, []))
        signals = _analyzer.analyze_session_signals(audit=audit, tool_records=records)
        all_signals.extend(signals)

    report = _analyzer.generate_role_insight(
        role=role_enum,
        evaluated_sessions=audits,
        all_signals=all_signals,
    )

    return RoleInsightReportResponse(
        role=report.role.value,
        evaluated_sessions_count=report.evaluated_sessions_count,
        total_saved_tokens_aggregate=report.total_saved_tokens_aggregate,
        total_cost_saved_usd_aggregate=report.total_cost_saved_usd_aggregate,
        top_efficiency_tools=report.top_efficiency_tools,
        identified_engineering_signals=[_convert_signal(s) for s in report.identified_engineering_signals],
        primary_bottleneck_summary=report.primary_bottleneck_summary,
    )
