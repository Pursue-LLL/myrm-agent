"""
[INPUT]: Inbound metric observations, path labels, and dynamic cap configuration requests.
[OUTPUT]: REST API endpoints exposing metric cardinality safeguards, stats, and overflow governance.
[POS]: myrm-agent/myrm-agent-server/app/api/system/metric_cardinality_api.py
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.cardinality_cap import (
    CardinalityCapConfig,
    CardinalityStatus,
    MetricCardinalityGovernor,
    MetricCardinalityStat,
)

router = APIRouter(prefix="/metric-cardinality", tags=["metric-cardinality"])

_default_governor = MetricCardinalityGovernor(
    CardinalityCapConfig(
        default_cap=128,
        warning_threshold=0.8,
        overflow_sentinel="_overflow_",
    )
)


def get_default_cardinality_governor() -> MetricCardinalityGovernor:
    return _default_governor


# --- Request/Response Models ---


class IngestSampleRequest(BaseModel):
    metric_name: str = Field(..., description="Target Prometheus metric name")
    label_value: str = Field(..., description="Raw label value or request path (e.g. /api/v1/sessions/12345)")


class IngestSampleResponse(BaseModel):
    metric_name: str
    original_label: str
    resolved_label: str
    is_overflow: bool


class ConfigureCapRequest(BaseModel):
    metric_name: str = Field(..., description="Target Prometheus metric name")
    cap_limit: int = Field(..., ge=1, description="New ceiling for distinct tracked labels")


# --- Endpoints ---


@router.post("/sample", response_model=IngestSampleResponse)
def ingest_sample(req: IngestSampleRequest) -> IngestSampleResponse:
    """Ingest a metric observation label, applying path normalization and cardinality cap guardrails."""
    gov = get_default_cardinality_governor()
    resolved_label, is_overflow = gov.normalize_or_cap(req.metric_name, req.label_value)
    return IngestSampleResponse(
        metric_name=req.metric_name,
        original_label=req.label_value,
        resolved_label=resolved_label,
        is_overflow=is_overflow,
    )


@router.get("/stats")
def get_cardinality_stats(
    metric_name: Optional[str] = Query(None, description="Optional filter by metric name")
) -> List[Dict[str, object]]:
    """Retrieve itemized cardinality statistics and overflow counts for governed metrics."""
    gov = get_default_cardinality_governor()
    stats: List[MetricCardinalityStat] = gov.get_metric_stats(metric_name)
    return [stat.model_dump() for stat in stats]


@router.post("/configure")
def configure_cap(req: ConfigureCapRequest) -> Dict[str, str]:
    """Dynamically configure the distinct label capacity limit for a metric."""
    gov = get_default_cardinality_governor()
    gov.configure_cap(req.metric_name, req.cap_limit)
    return {"status": "configured", "metric_name": req.metric_name, "cap_limit": str(req.cap_limit)}


@router.post("/reset")
def reset_governor() -> Dict[str, str]:
    """Reset the governor state for test isolation."""
    gov = get_default_cardinality_governor()
    gov.reset()
    return {"status": "reset"}
