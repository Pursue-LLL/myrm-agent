"""
[INPUT]: Runtime activity logs, period type queries, and daily task claims.
[OUTPUT]: REST API endpoints for multi-agent cross-period pivot reports, gamified milestones, and team insights.
[POS]: myrm-agent/myrm-agent-server/app/api/system/cross_period_milestone_api.py
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.cross_period_milestone import (
    AgentActivityEvent,
    AgentRuntimeUsagePoint,
    CrossPeriodMilestoneEngine,
    CrossPeriodPivotReport,
    DailyEfficiencyTask,
    MilestoneBadge,
    PeriodAggregateSummary,
    PeriodType,
    TeamAdoptionInsights,
    TeamMemberAdoptionItem,
    UserGamifiedProfile,
)

router = APIRouter(prefix="/cross-period-milestone", tags=["cross-period-milestone"])

_default_engine = CrossPeriodMilestoneEngine()


def get_default_cross_period_engine() -> CrossPeriodMilestoneEngine:
    return _default_engine


# --- Request/Response Models ---


class RecordActivityRequest(BaseModel):
    user_id: str = Field(..., description="Initiating user ID")
    user_name: str = Field(default="Employee", description="User display name")
    agent_id: str = Field(..., description="Invoked agent identifier")
    agent_name: str = Field(..., description="Invoked agent display name")
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    success: bool = Field(default=True)
    task_category: str = Field(default="general")
    timestamp_iso: Optional[str] = Field(default=None)


class ClaimDailyTaskRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    task_id: str = Field(..., description="Task ID to claim")


# --- Endpoints ---


@router.post("/activity")
def record_activity(req: RecordActivityRequest) -> Dict[str, str]:
    """Ingest a multi-agent invocation event to drive usage aggregation and gamified XP progression."""
    from datetime import datetime, timezone

    ts = req.timestamp_iso or datetime.now(timezone.utc).isoformat()
    event = AgentActivityEvent(
        user_id=req.user_id,
        user_name=req.user_name,
        agent_id=req.agent_id,
        agent_name=req.agent_name,
        tokens_in=req.tokens_in,
        tokens_out=req.tokens_out,
        cost_usd=req.cost_usd,
        latency_ms=req.latency_ms,
        success=req.success,
        task_category=req.task_category,
        timestamp_iso=ts,
    )
    engine = get_default_cross_period_engine()
    return engine.record_activity(event)


@router.get("/pivot-report")
def get_pivot_report(
    period_type: str = Query("weekly", description="weekly | monthly | quarterly | custom"),
    reference_date: Optional[str] = Query(None, description="ISO reference date"),
) -> Dict[str, object]:
    """Retrieve comparative multi-agent pivot report with per-agent breakdowns and period-over-period growth."""
    try:
        p_enum = PeriodType(period_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid period_type '{period_type}'")

    engine = get_default_cross_period_engine()
    report: CrossPeriodPivotReport = engine.generate_pivot_report(p_enum, reference_date)
    return report.model_dump()


@router.get("/gamification/{user_id}")
def get_user_gamification(
    user_id: str, user_name: str = Query("User", description="Display name")
) -> Dict[str, object]:
    """Retrieve gamified competency milestones, level progress, daily tasks and badges for a user."""
    engine = get_default_cross_period_engine()
    profile: UserGamifiedProfile = engine.get_user_gamified_profile(user_id, user_name)
    return profile.model_dump()


@router.post("/claim-task")
def claim_task(req: ClaimDailyTaskRequest) -> Dict[str, object]:
    """Claim or complete a daily efficiency quest to gain bonus XP."""
    engine = get_default_cross_period_engine()
    profile = engine.claim_daily_task(req.user_id, req.task_id)
    return profile.model_dump()


@router.get("/team-rankings")
def get_team_rankings() -> Dict[str, object]:
    """Retrieve team-level adoption insights and leaderboard."""
    engine = get_default_cross_period_engine()
    insights: TeamAdoptionInsights = engine.get_team_adoption_insights()
    return insights.model_dump()


@router.post("/reset")
def reset_engine() -> Dict[str, str]:
    """Reset the engine for isolated unit testing."""
    engine = get_default_cross_period_engine()
    engine.reset()
    return {"status": "reset"}
