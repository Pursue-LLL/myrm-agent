"""
[INPUT]: Diagnostic event emission payloads, session queries, and severity filter parameters.
[OUTPUT]: DiagnosticEventResponse, DiagnosticStreamStatsResponse, and decoupled event list endpoints.
[POS]: myrm-agent/myrm-agent-server/app/api/system/diagnostic_stream_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.diagnostic_stream import (
    DiagnosticCategory,
    DiagnosticEvent,
    DiagnosticSeverity,
    DiagnosticStreamDispatcher,
    DiagnosticStreamStats,
)

router = APIRouter(tags=["diagnostic-stream"])

_dispatcher = DiagnosticStreamDispatcher()


# --- Pydantic Schemas ---

class EmitDiagnosticEventRequest(BaseModel):
    session_id: str
    run_id: str
    category: str = "RETRY"  # RETRY | CONTEXT_TRUNCATION | MCP_LATENCY | SANDBOX_PRESSURE | MODEL_DEGRADE | CUSTOM
    severity: str = "WARNING"  # DEBUG | INFO | WARNING | ERROR | CRITICAL
    code: str
    message: str
    details: Dict[str, str] = Field(default_factory=dict)


class DiagnosticEventResponse(BaseModel):
    event_id: str
    session_id: str
    run_id: str
    category: str
    severity: str
    code: str
    message: str
    details: Dict[str, str]
    timestamp: str


class DiagnosticStreamStatsResponse(BaseModel):
    total_events: int
    by_severity: Dict[str, int]
    by_category: Dict[str, int]


# --- Helper Converters ---

def _to_event_response(e: DiagnosticEvent) -> DiagnosticEventResponse:
    return DiagnosticEventResponse(
        event_id=e.event_id,
        session_id=e.session_id,
        run_id=e.run_id,
        category=e.category.value,
        severity=e.severity.value,
        code=e.code,
        message=e.message,
        details=e.details,
        timestamp=e.timestamp,
    )


# --- Endpoints ---

@router.post(
    "/diagnostic-stream/emit",
    response_model=DiagnosticEventResponse,
    summary="向独立诊断通道派发事件（与普通用户消息流双轨隔离，杜绝聊天气泡污染）",
)
def emit_diagnostic_event(payload: EmitDiagnosticEventRequest) -> DiagnosticEventResponse:
    try:
        cat_enum = DiagnosticCategory(payload.category)
    except ValueError:
        cat_enum = DiagnosticCategory.CUSTOM

    try:
        sev_enum = DiagnosticSeverity(payload.severity)
    except ValueError:
        sev_enum = DiagnosticSeverity.INFO

    event = _dispatcher.dispatch_diagnostic(
        session_id=payload.session_id,
        run_id=payload.run_id,
        category=cat_enum,
        severity=sev_enum,
        code=payload.code,
        message=payload.message,
        details=payload.details,
    )
    return _to_event_response(event)


@router.get(
    "/diagnostic-stream/events",
    response_model=List[DiagnosticEventResponse],
    summary="查询最近诊断事件列表（支持按 session_id 与严重度筛选）",
)
def get_recent_diagnostic_events(
    session_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> List[DiagnosticEventResponse]:
    sev_enum: Optional[DiagnosticSeverity] = None
    if severity:
        try:
            sev_enum = DiagnosticSeverity(severity)
        except ValueError:
            sev_enum = None

    events = _dispatcher.get_recent_diagnostics(
        session_id=session_id,
        severity=sev_enum,
        limit=limit,
    )
    return [_to_event_response(e) for e in events]


@router.get(
    "/diagnostic-stream/stats",
    response_model=DiagnosticStreamStatsResponse,
    summary="获取诊断事件全景聚合统计（按严重等级与领域分布）",
)
def get_diagnostic_stream_stats() -> DiagnosticStreamStatsResponse:
    stats = _dispatcher.get_stats()
    return DiagnosticStreamStatsResponse(
        total_events=stats.total_events,
        by_severity=stats.by_severity,
        by_category=stats.by_category,
    )
