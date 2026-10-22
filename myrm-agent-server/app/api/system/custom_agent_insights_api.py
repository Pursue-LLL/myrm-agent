"""
[INPUT]: Custom agent interaction events, skill executions, HITL task frictions, and telemetry queries.
[OUTPUT]: Pydantic schemas and REST endpoints for Custom Agent Insights and Operational Observability.
[POS]: myrm-agent/myrm-agent-server/app/api/system/custom_agent_insights_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.agent_insights import (
    AgentHitlBottleneckMetric,
    AgentIntentCluster,
    AgentSkillHealthMetric,
    CustomAgentInsightsSnapshot,
    SkillExecutionStatus,
    get_default_agent_insights_tracker,
)

router = APIRouter(prefix="/custom-agent-insights", tags=["custom-agent-insights"])


# --- Pydantic Request & Response Schemas ---


class RecordInteractionRequest(BaseModel):
    agent_id: str = Field(..., description="Unique identifier of the custom agent")
    intent_category: str = Field(..., description="Categorized user scenario or intent")
    utterance: str = Field(default="N/A", description="Representative utterance or prompt summary")
    tokens: int = Field(default=0, ge=0, description="Tokens consumed in interaction")


class RecordSkillExecutionRequest(BaseModel):
    agent_id: str = Field(..., description="Unique identifier of the custom agent")
    skill_name: str = Field(..., description="Name of the executed skill or tool")
    latency_ms: float = Field(..., ge=0.0, description="Execution duration in milliseconds")
    status: str = Field(
        default="SUCCESS",
        description="SUCCESS, FAILURE, or TIMEOUT",
    )
    error_reason: str = Field(default="", description="Detailed failure or timeout cause")


class RecordHitlTaskRequest(BaseModel):
    agent_id: str = Field(..., description="Unique identifier of the custom agent")
    intercepted: bool = Field(..., description="Whether task required human intervention or approval")
    wait_seconds: float = Field(default=0.0, ge=0.0, description="Seconds waiting for human approval")
    deliverables_count: int = Field(default=1, ge=0, description="Artifacts or documents delivered")
    tokens_consumed: int = Field(default=0, ge=0, description="Total tokens spent during task")


class ResetAgentInsightsRequest(BaseModel):
    agent_id: Optional[str] = Field(default=None, description="Optional agent id to clear, or null for all")


class AgentIntentClusterModel(BaseModel):
    intent_category: str
    sample_utterance: str
    request_count: int
    share_pct: float


class AgentSkillHealthMetricModel(BaseModel):
    skill_name: str
    total_calls: int
    success_rate_pct: float
    avg_latency_ms: float
    p95_latency_ms: float
    top_error_reasons: List[str]


class AgentHitlBottleneckMetricModel(BaseModel):
    total_tasks: int
    hitl_intercepted_tasks: int
    hitl_interception_rate_pct: float
    avg_approval_wait_seconds: float
    token_roi_ratio: float


class CustomAgentInsightsResponse(BaseModel):
    agent_id: str
    time_window_days: int
    total_interactions: int
    total_tokens_consumed: int
    intent_clusters: List[AgentIntentClusterModel]
    skill_funnel: List[AgentSkillHealthMetricModel]
    hitl_metrics: AgentHitlBottleneckMetricModel
    generated_at_ms: int


# --- Helper Converters ---


def _to_insights_response(snapshot: CustomAgentInsightsSnapshot) -> CustomAgentInsightsResponse:
    clusters = [
        AgentIntentClusterModel(
            intent_category=c.intent_category,
            sample_utterance=c.sample_utterance,
            request_count=c.request_count,
            share_pct=c.share_pct,
        )
        for c in snapshot.intent_clusters
    ]

    funnel = [
        AgentSkillHealthMetricModel(
            skill_name=s.skill_name,
            total_calls=s.total_calls,
            success_rate_pct=s.success_rate_pct,
            avg_latency_ms=s.avg_latency_ms,
            p95_latency_ms=s.p95_latency_ms,
            top_error_reasons=list(s.top_error_reasons),
        )
        for s in snapshot.skill_funnel
    ]

    hitl = AgentHitlBottleneckMetricModel(
        total_tasks=snapshot.hitl_metrics.total_tasks,
        hitl_intercepted_tasks=snapshot.hitl_metrics.hitl_intercepted_tasks,
        hitl_interception_rate_pct=snapshot.hitl_metrics.hitl_interception_rate_pct,
        avg_approval_wait_seconds=snapshot.hitl_metrics.avg_approval_wait_seconds,
        token_roi_ratio=snapshot.hitl_metrics.token_roi_ratio,
    )

    return CustomAgentInsightsResponse(
        agent_id=snapshot.agent_id,
        time_window_days=snapshot.time_window_days,
        total_interactions=snapshot.total_interactions,
        total_tokens_consumed=snapshot.total_tokens_consumed,
        intent_clusters=clusters,
        skill_funnel=funnel,
        hitl_metrics=hitl,
        generated_at_ms=snapshot.generated_at_ms,
    )


# --- Endpoints ---


@router.get("/insights", response_model=CustomAgentInsightsResponse)
async def get_agent_insights(
    agent_id: str = Query(..., description="Target custom agent identifier"),
    window_days: int = Query(7, ge=1, le=90, description="Rolling time window in days"),
) -> CustomAgentInsightsResponse:
    """Retrieve multi-angle operational insights for a custom agent."""
    tracker = get_default_agent_insights_tracker()
    snapshot = tracker.get_insights_snapshot(agent_id=agent_id, window_days=window_days)
    return _to_insights_response(snapshot)


@router.post("/record-interaction")
async def record_interaction(req: RecordInteractionRequest) -> Dict[str, bool]:
    """Record an interaction query categorized into an intent scenario."""
    tracker = get_default_agent_insights_tracker()
    tracker.record_interaction(
        agent_id=req.agent_id,
        intent_category=req.intent_category,
        utterance=req.utterance,
        tokens=req.tokens,
    )
    return {"ok": True}


@router.post("/record-skill")
async def record_skill_execution(req: RecordSkillExecutionRequest) -> Dict[str, bool]:
    """Record an execution outcome and latency for an agent skill."""
    tracker = get_default_agent_insights_tracker()
    tracker.record_skill_execution(
        agent_id=req.agent_id,
        skill_name=req.skill_name,
        latency_ms=req.latency_ms,
        status=req.status,
        error_reason=req.error_reason,
    )
    return {"ok": True}


@router.post("/record-hitl")
async def record_hitl_task(req: RecordHitlTaskRequest) -> Dict[str, bool]:
    """Record task completion with human approval friction and token ROI."""
    tracker = get_default_agent_insights_tracker()
    tracker.record_hitl_task(
        agent_id=req.agent_id,
        intercepted=req.intercepted,
        wait_seconds=req.wait_seconds,
        deliverables_count=req.deliverables_count,
        tokens_consumed=req.tokens_consumed,
    )
    return {"ok": True}


@router.post("/reset")
async def reset_agent_insights(
    req: Optional[ResetAgentInsightsRequest] = None,
) -> Dict[str, bool]:
    """Reset telemetry history for a specific custom agent or all agents."""
    tracker = get_default_agent_insights_tracker()
    aid = req.agent_id if req else None
    tracker.reset(agent_id=aid)
    return {"ok": True}
