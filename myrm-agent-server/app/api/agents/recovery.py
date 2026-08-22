"""Agent profile startup recovery, fault isolation, and last-known-good rollback endpoints.

[INPUT]
services.agent.profile.profile_recovery_service::ProfileStartupRecoveryService
services.agent.profile.profile_snapshot_service::ProfileSnapshotService

[OUTPUT]
GET  /agents/{agent_id}/recovery/health      : Probe profile components health
POST /agents/{agent_id}/recovery/rollback    : Rollback to last-known-good snapshot
GET  /agents/{agent_id}/recovery/diagnostics : Export full recovery diagnostic bundle

[POS]
Agent 启动恢复与容灾 API。
提供 Last-Known-Good 回滚、组件故障探针和排障诊断包导出。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.utils.errors import StandardHTTPException, internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.agent.profile.profile_recovery_service import (
    ProfileStartupRecoveryService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/{agent_id}/recovery", tags=["Agent Recovery"])


@router.get("/health", response_model=StandardSuccessResponse)
async def get_profile_recovery_health(agent_id: str) -> JSONResponse:
    """Probe agent profile configuration and return component health status."""
    try:
        report = await ProfileStartupRecoveryService.probe_profile_health(agent_id)
        return success_response(
            data={
                "agent_id": report.agent_id,
                "is_healthy": report.is_healthy,
                "healthy_components": [
                    {
                        "component_type": c.component_type,
                        "component_id": c.component_id,
                        "status": c.status,
                        "error_message": c.error_message,
                    }
                    for c in report.healthy_components
                ],
                "quarantined_components": [
                    {
                        "component_type": c.component_type,
                        "component_id": c.component_id,
                        "status": c.status,
                        "error_message": c.error_message,
                    }
                    for c in report.quarantined_components
                ],
                "has_last_known_good": report.has_last_known_good,
                "last_known_good_id": report.last_known_good_id,
                "timestamp": report.timestamp,
            }
        )
    except Exception as exc:
        raise internal_error(operation="Probe profile health", exception=exc) from exc


@router.post("/rollback", response_model=StandardSuccessResponse)
async def rollback_profile_to_last_known_good(agent_id: str) -> JSONResponse:
    """Roll back agent profile to its last-known-good snapshot."""
    try:
        success = await ProfileStartupRecoveryService.rollback_to_last_known_good(agent_id)
        if not success:
            raise not_found_error(resource=f"Last-known-good snapshot for agent {agent_id}")
        return success_response(data={"agent_id": agent_id, "rolled_back": True})
    except Exception as exc:
        if isinstance(exc, StandardHTTPException):
            raise exc
        raise internal_error(operation="Rollback to last-known-good", exception=exc) from exc


@router.get("/diagnostics", response_model=StandardSuccessResponse)
async def export_profile_recovery_diagnostics(agent_id: str) -> JSONResponse:
    """Export detailed recovery diagnostics bundle for debugging."""
    try:
        diagnostics = await ProfileStartupRecoveryService.export_diagnostics(agent_id)
        return success_response(data={"diagnostics": diagnostics})
    except Exception as exc:
        raise internal_error(operation="Export profile diagnostics", exception=exc) from exc
