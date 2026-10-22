"""
[INPUT]: Inbound HTTP visit telemetry, User-Agent headers, and documentation content payloads.
[OUTPUT]: Agentic traffic analytics summaries, AEO page diagnostics, and 4-tier conversion funnels.
[POS]: myrm-agent/myrm-agent-server/app/api/system/agentic_traffic_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.agentic_traffic import (
    AgentAbandonmentSentinel,
    AgenticTrafficAnalyticsEngine,
)

router = APIRouter(tags=["agentic-traffic"])

_engine = AgenticTrafficAnalyticsEngine()
_sentinel = AgentAbandonmentSentinel()


class RecordVisitRequest(BaseModel):
    visit_id: str
    user_agent: str
    target_path: str
    headers: Dict[str, str] = Field(default_factory=dict)
    duration_ms: float = 0.0
    status_code: int = 200
    page_content: Optional[str] = None
    has_llms_txt_declared: bool = False


class DiagnosePageRequest(BaseModel):
    path: str
    content: str
    has_llms_txt_declared: bool = False


class AgentVisitRecordSchema(BaseModel):
    visit_id: str
    agent_type: str
    user_agent: str
    target_path: str
    duration_ms: float
    status_code: int
    is_agent: bool
    confidence_score: float
    funnel_stage: str
    abandonment_reasons: List[str]
    timestamp: str


class AeoPageDiagnosticResponse(BaseModel):
    path: str
    estimated_tokens: int
    has_llms_txt_declared: bool
    has_code_in_first_500_tokens: bool
    is_spa_client_blank: bool
    suggested_actions: List[str]
    abandonment_reasons: List[str]
    aeo_score: int


class AgentTrafficSummaryResponse(BaseModel):
    total_visits: int
    agent_visits_count: int
    human_visits_count: int
    agent_traffic_ratio_pct: float
    top_agents: Dict[str, int]
    funnel_conversion: Dict[str, int]
    abandonment_distribution: Dict[str, int]
    recent_visits: List[AgentVisitRecordSchema]
    generated_at: str


@router.post(
    "/agentic-traffic/record-visit",
    response_model=AgentVisitRecordSchema,
    status_code=status.HTTP_200_OK,
)
async def record_visit(req: RecordVisitRequest) -> AgentVisitRecordSchema:
    """Records an incoming HTTP visit, classifies whether it is a Coding Agent, and runs AEO analysis."""
    record = _engine.record_visit(
        visit_id=req.visit_id,
        user_agent=req.user_agent,
        target_path=req.target_path,
        headers=req.headers,
        duration_ms=req.duration_ms,
        status_code=req.status_code,
        page_content=req.page_content,
        has_llms_txt_declared=req.has_llms_txt_declared,
    )
    return AgentVisitRecordSchema(
        visit_id=record.visit_id,
        agent_type=record.agent_type.value,
        user_agent=record.user_agent,
        target_path=record.target_path,
        duration_ms=record.duration_ms,
        status_code=record.status_code,
        is_agent=record.is_agent,
        confidence_score=record.confidence_score,
        funnel_stage=record.funnel_stage.value,
        abandonment_reasons=[r.value for r in record.abandonment_reasons],
        timestamp=record.timestamp,
    )


@router.get(
    "/agentic-traffic/analytics",
    response_model=AgentTrafficSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_agentic_traffic_analytics() -> AgentTrafficSummaryResponse:
    """Retrieves high-level summary of AI agent visits, conversion funnel, and abandonment breakdown."""
    summary = _engine.get_summary()
    return AgentTrafficSummaryResponse(
        total_visits=summary.total_visits,
        agent_visits_count=summary.agent_visits_count,
        human_visits_count=summary.human_visits_count,
        agent_traffic_ratio_pct=summary.agent_traffic_ratio_pct,
        top_agents=summary.top_agents,
        funnel_conversion=summary.funnel_conversion,
        abandonment_distribution=summary.abandonment_distribution,
        recent_visits=[
            AgentVisitRecordSchema(
                visit_id=v.visit_id,
                agent_type=v.agent_type.value,
                user_agent=v.user_agent,
                target_path=v.target_path,
                duration_ms=v.duration_ms,
                status_code=v.status_code,
                is_agent=v.is_agent,
                confidence_score=v.confidence_score,
                funnel_stage=v.funnel_stage.value,
                abandonment_reasons=[r.value for r in v.abandonment_reasons],
                timestamp=v.timestamp,
            )
            for v in summary.recent_visits
        ],
        generated_at=summary.generated_at,
    )


@router.post(
    "/agentic-traffic/diagnose-page",
    response_model=AeoPageDiagnosticResponse,
    status_code=status.HTTP_200_OK,
)
async def diagnose_page_aeo(req: DiagnosePageRequest) -> AeoPageDiagnosticResponse:
    """Performs real-time Agent Engine Optimization (AEO) inspection on raw page markdown or HTML."""
    diag = _sentinel.diagnose_page(
        path=req.path,
        content=req.content,
        has_llms_txt_declared=req.has_llms_txt_declared,
    )
    return AeoPageDiagnosticResponse(
        path=diag.path,
        estimated_tokens=diag.estimated_tokens,
        has_llms_txt_declared=diag.has_llms_txt_declared,
        has_code_in_first_500_tokens=diag.has_code_in_first_500_tokens,
        is_spa_client_blank=diag.is_spa_client_blank,
        suggested_actions=diag.suggested_actions,
        abandonment_reasons=[r.value for r in diag.abandonment_reasons],
        aeo_score=diag.aeo_score,
    )
