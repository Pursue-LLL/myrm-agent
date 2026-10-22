"""
[INPUT]: Raw span records, execution durations, active skill identifiers, and trace attributes.
[OUTPUT]: REST API endpoints for active skill span telemetry, attribute injection verification, and per-skill latency reports.
[POS]: myrm-agent/myrm-agent-server/app/api/system/active_skill_telemetry_api.py
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.active_skill_telemetry import (
    ACTIVE_SKILL_ATTRIBUTE_KEY,
    ActiveSkillSpanProcessor,
    ActiveSkillTelemetryReport,
    SkillSpanRecord,
    SkillTelemetryAggregation,
)

router = APIRouter(prefix="/active-skill-telemetry", tags=["active-skill-telemetry"])

_default_processor = ActiveSkillSpanProcessor()


def get_default_span_processor() -> ActiveSkillSpanProcessor:
    return _default_processor


# --- Request Models ---


class RecordSpanRequest(BaseModel):
    name: str = Field(..., description="Span operation name, e.g. 'llm.generate' or 'tool.bash'")
    duration_ms: float = Field(..., ge=0.0)
    trace_id: Optional[str] = Field(default=None)
    span_id: Optional[str] = Field(default=None)
    active_skill: Optional[str] = Field(default=None, description="Active skill name, e.g. 'git_master'")
    status: str = Field(default="ok", description="'ok' or 'error'")
    attributes: Dict[str, str] = Field(default_factory=dict)
    timestamp_ms: Optional[int] = Field(default=None)


# --- Endpoints ---


@router.post("/record-span", response_model=SkillSpanRecord)
def record_skill_span(req: RecordSpanRequest) -> SkillSpanRecord:
    """Record an execution span, auto-injecting myrm.skill.active attribute if correlated with an active skill."""
    processor = get_default_span_processor()
    return processor.record_span(
        name=req.name,
        duration_ms=req.duration_ms,
        trace_id=req.trace_id,
        span_id=req.span_id,
        active_skill=req.active_skill,
        status=req.status,
        attributes=req.attributes,
        timestamp_ms=req.timestamp_ms,
    )


@router.get("/report", response_model=ActiveSkillTelemetryReport)
def get_telemetry_report() -> ActiveSkillTelemetryReport:
    """Retrieve full active skill telemetry aggregation including P95 latency and error rate partitioned by skill."""
    processor = get_default_span_processor()
    return processor.get_report()


@router.get("/spans", response_model=List[SkillSpanRecord])
def get_skill_spans(
    skill_name: Optional[str] = Query(default=None, description="Optional filter by active skill"),
    limit: int = Query(default=50, ge=1, le=500),
) -> List[SkillSpanRecord]:
    """Retrieve recorded telemetry spans with optional active skill filter."""
    processor = get_default_span_processor()
    spans = processor.get_spans(skill_name=skill_name)
    return spans[-limit:]


@router.post("/reset")
def reset_telemetry() -> Dict[str, str]:
    """Clear recorded spans for test isolation."""
    processor = get_default_span_processor()
    processor.reset()
    return {"status": "reset_completed"}
