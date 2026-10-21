"""Cron usage statistics REST endpoint.

[INPUT]
- app.core.cron.adapters.sqlalchemy_aggregation (POS: SQL aggregation for token usage)
- cron.schemas (POS: usage stats Pydantic models)

[OUTPUT]
- GET /stats/usage — token usage aggregation

[POS]
Cron usage statistics REST endpoint. Provides token usage analytics.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.cron.schemas import (
    UsageByDay,
    UsageByJob,
    UsageByModel,
    UsageStatsResponse,
    UsageSummary,
)

router = APIRouter()

USER_ID = "default"


@router.get("/stats/usage", response_model=UsageStatsResponse)
async def usage_stats(
    days: int = Query(7, ge=1, le=365),
) -> UsageStatsResponse:
    from app.core.cron.adapters.sqlalchemy_aggregation import aggregate_usage

    result = await aggregate_usage(USER_ID, days=days)
    return UsageStatsResponse(
        summary=UsageSummary(**result["summary"]),
        by_day=[UsageByDay(**d) for d in result["by_day"]],
        by_job=[UsageByJob(**j) for j in result["by_job"]],
        by_model=[UsageByModel(**m) for m in result["by_model"]],
    )
