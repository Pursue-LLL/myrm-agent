"""Connector health monitoring REST endpoints for cron automations.

[INPUT]
- app.services.cron.connector_health_service::ConnectorHealthService (POS: 连接器健康聚合服务)
- app.api.cron.schemas::ConnectorsHealthListResponse, ConnectorHealthResponse (POS: 连接器健康响应模型)

[OUTPUT]
- GET /connectors/health — Query aggregated connector degradation matrix and health summaries

[POS]
Server REST API router for automation outbound connector degradation diagnostics.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.cron.schemas import (
    ConnectorHealthResponse,
    ConnectorsHealthListResponse,
)
from app.services.cron.connector_health_service import ConnectorHealthService

router = APIRouter()


@router.get("/connectors/health", response_model=ConnectorsHealthListResponse)
async def get_connectors_health(
    window_hours: int = Query(default=24, ge=1, le=168),
) -> ConnectorsHealthListResponse:
    """Get aggregated health metrics and degradation status across all outbound connectors."""
    summaries = await ConnectorHealthService.get_all_connectors_health(
        window_hours=window_hours,
    )

    items = [
        ConnectorHealthResponse(
            target=s.target,
            channel=s.channel,
            status=s.status.value,
            total_deliveries=s.total_deliveries,
            failed_deliveries=s.failed_deliveries,
            consecutive_failures=s.consecutive_failures,
            last_status_code=s.last_status_code,
            last_error_category=s.last_error_category.value if s.last_error_category else None,
            last_error_message=s.last_error_message,
            last_delivery_at=s.last_delivery_at,
            last_failed_at=s.last_failed_at,
            fix_suggestion=s.fix_suggestion,
            bound_job_ids=list(s.bound_job_ids),
        )
        for s in summaries
    ]

    degraded_count = sum(1 for s in summaries if s.status.value == "degraded")
    down_count = sum(1 for s in summaries if s.status.value == "down")

    return ConnectorsHealthListResponse(
        items=items,
        total=len(items),
        degraded_count=degraded_count,
        down_count=down_count,
    )


__all__ = ["router"]
