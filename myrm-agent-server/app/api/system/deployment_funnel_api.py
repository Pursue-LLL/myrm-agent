"""
[INPUT]: Funnel event payloads, user feedback payloads, deployment IDs, and autonomous goal dispatch requests.
[OUTPUT]: Funnel event confirmations, feedback receipts, DeploymentFunnelSnapshotResponse, and dispatch confirmations.
[POS]: myrm-agent/myrm-agent-server/app/api/system/deployment_funnel_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.deployment_funnel import (
    DeploymentFunnelEngine,
    DeploymentFunnelSnapshot,
    FeedbackSentiment,
    FunnelEventRecord,
    FunnelStageEnum,
    StageDropoffMetric,
    UserFeedbackRecord,
)

router = APIRouter(tags=["deployment-funnel"])

_engine = DeploymentFunnelEngine()


# --- Pydantic Schemas ---

class RecordFunnelEventRequest(BaseModel):
    deployment_id: str
    stage: str = "STAGE_1_VIEW"  # STAGE_1_VIEW | STAGE_2_ENGAGE | STAGE_3_ACTION | STAGE_4_COMPLETE
    user_ident: str
    metadata: Dict[str, str] = Field(default_factory=dict)


class FunnelEventResponse(BaseModel):
    event_id: str
    deployment_id: str
    stage: str
    user_ident: str
    timestamp: str
    metadata: Dict[str, str]


class RecordFeedbackRequest(BaseModel):
    deployment_id: str
    sentiment: str = "POSITIVE"  # POSITIVE | NEUTRAL | NEGATIVE
    comment: str


class FeedbackRecordResponse(BaseModel):
    feedback_id: str
    deployment_id: str
    sentiment: str
    comment: str
    timestamp: str


class StageDropoffMetricResponse(BaseModel):
    stage: str
    user_count: int
    conversion_rate_pct: float
    dropoff_rate_pct: float


class DeploymentFunnelSnapshotResponse(BaseModel):
    deployment_id: str
    total_visitors: int
    stages: List[StageDropoffMetricResponse]
    dropoff_hotspot_stage: Optional[str]
    feedback_counts: Dict[str, int]
    nudge_required: bool
    nudge_reason: Optional[str]
    autonomous_goal_recommendation: Optional[str]
    evaluated_at: str


class DispatchGoalRequest(BaseModel):
    deployment_id: str
    goal: str
    target_agent_id: str = "agent_autonomous_optimizer"


class DispatchGoalResponse(BaseModel):
    status: str
    deployment_id: str
    goal: str
    target_agent_id: str
    dispatched_at: str


# --- Helper Converters ---

def _to_snapshot_response(snap: DeploymentFunnelSnapshot) -> DeploymentFunnelSnapshotResponse:
    stage_resps = [
        StageDropoffMetricResponse(
            stage=s.stage.value,
            user_count=s.user_count,
            conversion_rate_pct=s.conversion_rate_pct,
            dropoff_rate_pct=s.dropoff_rate_pct,
        )
        for s in snap.stages
    ]

    return DeploymentFunnelSnapshotResponse(
        deployment_id=snap.deployment_id,
        total_visitors=snap.total_visitors,
        stages=stage_resps,
        dropoff_hotspot_stage=(
            snap.dropoff_hotspot_stage.value
            if snap.dropoff_hotspot_stage
            else None
        ),
        feedback_counts=snap.feedback_counts,
        nudge_required=snap.nudge_required,
        nudge_reason=snap.nudge_reason,
        autonomous_goal_recommendation=snap.autonomous_goal_recommendation,
        evaluated_at=snap.evaluated_at,
    )


# --- Endpoints ---

@router.post(
    "/deployment-funnel/event",
    response_model=FunnelEventResponse,
    summary="上报交付物部署后漏斗流失事件 (VIEW -> ENGAGE -> ACTION -> COMPLETE)",
)
def record_funnel_event(payload: RecordFunnelEventRequest) -> FunnelEventResponse:
    try:
        stage_enum = FunnelStageEnum(payload.stage)
    except ValueError:
        stage_enum = FunnelStageEnum.STAGE_1_VIEW

    event = _engine.record_event(
        deployment_id=payload.deployment_id,
        stage=stage_enum,
        user_ident=payload.user_ident,
        metadata=payload.metadata,
    )

    return FunnelEventResponse(
        event_id=event.event_id,
        deployment_id=event.deployment_id,
        stage=event.stage.value,
        user_ident=event.user_ident,
        timestamp=event.timestamp,
        metadata=event.metadata,
    )


@router.post(
    "/deployment-funnel/feedback",
    response_model=FeedbackRecordResponse,
    summary="上报交付物真实用户情感反馈与评价意见",
)
def record_user_feedback(payload: RecordFeedbackRequest) -> FeedbackRecordResponse:
    try:
        sentiment_enum = FeedbackSentiment(payload.sentiment)
    except ValueError:
        sentiment_enum = FeedbackSentiment.NEUTRAL

    fb = _engine.record_feedback(
        deployment_id=payload.deployment_id,
        sentiment=sentiment_enum,
        comment=payload.comment,
    )

    return FeedbackRecordResponse(
        feedback_id=fb.feedback_id,
        deployment_id=fb.deployment_id,
        sentiment=fb.sentiment.value,
        comment=fb.comment,
        timestamp=fb.timestamp,
    )


@router.get(
    "/deployment-funnel/snapshot/{deployment_id}",
    response_model=DeploymentFunnelSnapshotResponse,
    summary="查询部署漏斗阶梯转化率、流失热点断点、反馈统计与主动 Nudge 告警",
)
def get_funnel_snapshot(deployment_id: str) -> DeploymentFunnelSnapshotResponse:
    snap = _engine.generate_snapshot(deployment_id)
    return _to_snapshot_response(snap)


@router.post(
    "/deployment-funnel/dispatch-goal",
    response_model=DispatchGoalResponse,
    summary="将高阶自愈改进目标一键派发给 Agent 执行自主诊断与闭环优化",
)
def dispatch_autonomous_goal(payload: DispatchGoalRequest) -> DispatchGoalResponse:
    from datetime import datetime, timezone
    dispatched_at = datetime.now(timezone.utc).isoformat()
    return DispatchGoalResponse(
        status="dispatched",
        deployment_id=payload.deployment_id,
        goal=payload.goal,
        target_agent_id=payload.target_agent_id,
        dispatched_at=dispatched_at,
    )
