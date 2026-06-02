"""Rate Limits API.

[INPUT]
- myrm_agent_harness.toolkits.llms.rate_limit::RateLimitTracker (POS: Rate limit tracking)
- app.api.dependencies::get_deploy_identity (POS: Auth dependency)

[OUTPUT]
- GET /api/statistics/rate-limits

[POS]
API endpoints for fetching real-time rate limit statistics.
"""

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.llms.rate_limit import RateLimitTracker
from pydantic import BaseModel

from app.api.dependencies import get_deploy_identity
from app.core.infra.limiter import limiter

router = APIRouter()


class RateLimitBucketResponse(BaseModel):
    limit: int
    remaining: int
    reset_seconds: float
    updated_at: float
    usage_pct: float
    remaining_seconds_now: float


class RateLimitStateResponse(BaseModel):
    provider: str
    model: str
    rpm: RateLimitBucketResponse | None = None
    rph: RateLimitBucketResponse | None = None
    tpm: RateLimitBucketResponse | None = None
    tph: RateLimitBucketResponse | None = None
    highest_usage_pct: float
    updated_at: float


class RateLimitsResponse(BaseModel):
    states: list[RateLimitStateResponse]


@router.get(
    "/rate-limits",
    response_model=RateLimitsResponse,
    summary="Get real-time rate limits",
    description="Fetch the current rate limit states for all tracked LLM providers.",
)
@limiter.limit("30/minute")
async def get_rate_limits(
    user_id: str | None = Depends(get_deploy_identity),
) -> RateLimitsResponse:
    """Get current rate limit states."""
    tracker = RateLimitTracker.get()
    states = tracker.get_all_states()

    # Convert to Pydantic response models
    response_states = []
    for state in states:
        state_dict = state.to_dict()
        response_states.append(RateLimitStateResponse(**state_dict))

    return RateLimitsResponse(states=response_states)
