"""
[INPUT]: Rate limit events, failure signals, and metrics query parameters.
[OUTPUT]: Partitioned rate limit metrics, provider failure attributions, and consistency flags.
[POS]: myrm-agent/myrm-agent-server/app/api/system/rate_limit_split_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.rate_limit_split import (
    FailureEvent,
    RateLimitEvent,
    RateLimitMetricsSnapshot,
    RateLimitSource,
    get_default_rate_limit_tracker,
)

router = APIRouter(prefix="/rate-limit-split", tags=["rate-limit-split"])


# --- Pydantic Request & Response Schemas ---

class RecordRateLimitRequest(BaseModel):
    source: str = Field(default="upstream", description="myrm or upstream")
    provider: Optional[str] = Field(default=None, description="Model provider name")
    model: Optional[str] = Field(default=None, description="Specific model name")
    reason: Optional[str] = Field(default=None, description="Rejection reason or diagnostic details")


class RecordFailureRequest(BaseModel):
    provider: Optional[str] = Field(default=None, description="Model provider name")
    model: Optional[str] = Field(default=None, description="Specific model name")
    error_code: Optional[str] = Field(default=None, description="Upstream or internal error code")
    reason: Optional[str] = Field(default=None, description="Diagnostic reason")


class RecordCompletedRequest(BaseModel):
    provider: Optional[str] = Field(default=None, description="Model provider name")
    model: Optional[str] = Field(default=None, description="Specific model name")


class RateLimitEventModel(BaseModel):
    source: str
    provider: str
    model: str
    timestamp_ms: int
    reason: str


class FailureEventModel(BaseModel):
    provider: str
    model: str
    error_code: str
    timestamp_ms: int
    reason: str


class RateLimitMetricsResponse(BaseModel):
    total_requests: int
    total_completed: int
    total_rate_limited: int
    rate_limited_by_source: Dict[str, int]
    total_failed: int
    failed_by_provider: Dict[str, int]
    totals_consistent: bool
    recent_rate_limit_events: List[RateLimitEventModel]
    recent_failure_events: List[FailureEventModel]


# --- Helper Converters ---

def _to_rate_limit_event_model(event: RateLimitEvent) -> RateLimitEventModel:
    return RateLimitEventModel(
        source=event.source.value,
        provider=event.provider,
        model=event.model,
        timestamp_ms=event.timestamp_ms,
        reason=event.reason,
    )


def _to_failure_event_model(event: FailureEvent) -> FailureEventModel:
    return FailureEventModel(
        provider=event.provider,
        model=event.model,
        error_code=event.error_code,
        timestamp_ms=event.timestamp_ms,
        reason=event.reason,
    )


def _to_metrics_response(snapshot: RateLimitMetricsSnapshot) -> RateLimitMetricsResponse:
    return RateLimitMetricsResponse(
        total_requests=snapshot.total_requests,
        total_completed=snapshot.total_completed,
        total_rate_limited=snapshot.total_rate_limited,
        rate_limited_by_source=snapshot.rate_limited_by_source,
        total_failed=snapshot.total_failed,
        failed_by_provider=snapshot.failed_by_provider,
        totals_consistent=snapshot.totals_consistent,
        recent_rate_limit_events=[_to_rate_limit_event_model(e) for e in snapshot.recent_rate_limit_events],
        recent_failure_events=[_to_failure_event_model(e) for e in snapshot.recent_failure_events],
    )


# --- Endpoints ---

@router.get("/metrics", response_model=RateLimitMetricsResponse)
async def get_metrics() -> RateLimitMetricsResponse:
    """Retrieve full rate limit split metrics, invariant totals, and event attribution."""
    tracker = get_default_rate_limit_tracker()
    snapshot = tracker.get_snapshot()
    return _to_metrics_response(snapshot)


@router.post("/record-rate-limit", response_model=RateLimitEventModel)
async def record_rate_limit(req: RecordRateLimitRequest) -> RateLimitEventModel:
    """Record a 429 rate limit event partitioned into myrm vs upstream."""
    tracker = get_default_rate_limit_tracker()
    source_val = RateLimitSource.MYRM if req.source.lower() in ("myrm", "local", "governor") else RateLimitSource.UPSTREAM
    event = tracker.record_rate_limit(
        source=source_val,
        provider=req.provider,
        model=req.model,
        reason=req.reason,
    )
    return _to_rate_limit_event_model(event)


@router.post("/record-failure", response_model=FailureEventModel)
async def record_failure(req: RecordFailureRequest) -> FailureEventModel:
    """Record a non-429 request failure attributed to a specific provider."""
    tracker = get_default_rate_limit_tracker()
    event = tracker.record_failure(
        provider=req.provider,
        model=req.model,
        error_code=req.error_code,
        reason=req.reason,
    )
    return _to_failure_event_model(event)


@router.post("/record-completed")
async def record_completed(req: RecordCompletedRequest) -> Dict[str, bool]:
    """Record a completed, non-rate-limited and non-failed request."""
    tracker = get_default_rate_limit_tracker()
    tracker.record_completed(provider=req.provider, model=req.model)
    return {"ok": True}


@router.post("/reset")
async def reset_metrics() -> Dict[str, bool]:
    """Reset counters and event buffers (for testing and debugging)."""
    tracker = get_default_rate_limit_tracker()
    tracker.reset()
    return {"ok": True}
