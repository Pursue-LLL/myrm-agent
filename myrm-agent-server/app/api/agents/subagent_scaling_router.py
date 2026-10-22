"""FastAPI router for Subagent Concurrency & Tool Budget Adaptive Scaling (Item 31).

[INPUT]
- app.schemas.subagent_scaling::{SubagentConfigMigrationRequest, WatermarkHeartbeatRequest, ...}
- app.services.agent.subagent_scaling_service::{SubagentScalingService, get_subagent_scaling_service}

[OUTPUT]
- Router mounted under /agents/subagents/scaling.

[POS]
- HTTP endpoints for zero-disruption configuration migration,
  80% watermark heartbeats, and supervision HUD alert controls.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.subagent_scaling import (
    SubagentConfigMigrationRequest,
    WatermarkHeartbeatRequest,
)
from app.services.agent.subagent_scaling_service import (
    SubagentScalingService,
    get_subagent_scaling_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subagents/scaling", tags=["subagents-scaling"])


@router.post(
    "/migrate-config",
    response_model=StandardSuccessResponse,
    summary="Evaluate and adapt legacy subagent configuration defaults",
)
def migrate_config_endpoint(
    req: SubagentConfigMigrationRequest,
    service: SubagentScalingService = Depends(get_subagent_scaling_service),
) -> StandardSuccessResponse:
    """Detect legacy defaults {concurrency in (3,5), turns in (25,50)} and lift smoothly to modern scaled quotas."""
    migration_result = service.migrate_configuration(req)
    return create_success_response(data=migration_result)


@router.post(
    "/watermark-heartbeat",
    response_model=StandardSuccessResponse,
    summary="Emit execution turn heartbeat and monitor 80% watermark",
)
def watermark_heartbeat_endpoint(
    req: WatermarkHeartbeatRequest,
    service: SubagentScalingService = Depends(get_subagent_scaling_service),
) -> StandardSuccessResponse:
    """Record execution turn progress and fire pre-warning alert upon crossing 80% watermark."""
    heartbeat_result = service.process_heartbeat(req)
    return create_success_response(data=heartbeat_result)


@router.get(
    "/sessions/{session_id}/watermark-alerts",
    response_model=StandardSuccessResponse,
    summary="List active and persisted watermark alerts for a session",
)
def get_session_watermark_alerts_endpoint(
    session_id: str = Path(..., description="Unique chat session identifier"),
    service: SubagentScalingService = Depends(get_subagent_scaling_service),
) -> StandardSuccessResponse:
    """Retrieve recorded watermark pre-warning alerts for supervision HUD."""
    alerts = service.get_alerts(session_id)
    return create_success_response(data=alerts)


@router.post(
    "/sessions/{session_id}/watermark-alerts/{subagent_id}/dismiss",
    response_model=StandardSuccessResponse,
    summary="Dismiss an active watermark alert",
)
def dismiss_watermark_alert_endpoint(
    session_id: str = Path(..., description="Unique chat session identifier"),
    subagent_id: str = Path(..., description="Subagent task identifier"),
    service: SubagentScalingService = Depends(get_subagent_scaling_service),
) -> StandardSuccessResponse:
    """Acknowledge and dismiss an active watermark warning."""
    dismissed = service.dismiss_alert(session_id, subagent_id)
    return create_success_response(data={"dismissed": dismissed, "subagent_id": subagent_id})


@router.post(
    "/sessions/{session_id}/watermark-alerts/{subagent_id}/expand",
    response_model=StandardSuccessResponse,
    summary="Expand turn budget and clear watermark guard for subagent",
)
def expand_subagent_budget_endpoint(
    session_id: str = Path(..., description="Unique chat session identifier"),
    subagent_id: str = Path(..., description="Subagent task identifier"),
    service: SubagentScalingService = Depends(get_subagent_scaling_service),
) -> StandardSuccessResponse:
    """Grant additional budget and reset watermark guard so task continues safely."""
    expanded = service.expand_budget(session_id, subagent_id)
    return create_success_response(data={"expanded": expanded, "subagent_id": subagent_id})


@router.delete(
    "/sessions/{session_id}/watermark-alerts",
    response_model=StandardSuccessResponse,
    summary="Clear all watermark alerts and tracking state for session",
)
def cleanup_session_watermark_alerts_endpoint(
    session_id: str = Path(..., description="Unique chat session identifier"),
    service: SubagentScalingService = Depends(get_subagent_scaling_service),
) -> StandardSuccessResponse:
    """Release all monitoring guard and alert resources for terminated session."""
    cleaned = service.cleanup_session(session_id)
    return create_success_response(data={"cleaned": cleaned, "session_id": session_id})
