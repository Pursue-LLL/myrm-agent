"""FastAPI router for External Plugin Guardrail Auditing and Migration Doctor.

[INPUT]
- PluginAuditRequest, MigrationDiagnoseRequest, MigrationExecuteRequest payloads.

[OUTPUT]
- PluginAuditReportResponse, MigrationDoctorReportResponse, MigrationExecuteResponse.

[POS]
- app.api.security.plugin_guardrail_router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.plugin_guardrail import (
    MigrationDiagnoseRequest,
    MigrationDoctorReportResponse,
    MigrationExecuteRequest,
    MigrationExecuteResponse,
    PluginAuditReportResponse,
    PluginAuditRequest,
)
from app.services.security.plugin_guardrail_service import (
    PluginGuardrailService,
    get_plugin_guardrail_service,
)

router = APIRouter(
    prefix="/security/plugin-guardrails",
    tags=["Security - External Plugin Guardrails & Migration Doctor"],
)


@router.post("/audit", response_model=PluginAuditReportResponse)
async def audit_plugin(
    payload: PluginAuditRequest,
    service: PluginGuardrailService = Depends(get_plugin_guardrail_service),
) -> PluginAuditReportResponse:
    """Perform static code auditing, AST check, and capability scoping for an external plugin."""
    return service.audit_plugin(payload)


@router.post("/diagnose-migration", response_model=MigrationDoctorReportResponse)
async def diagnose_migration(
    payload: MigrationDiagnoseRequest,
    service: PluginGuardrailService = Depends(get_plugin_guardrail_service),
) -> MigrationDoctorReportResponse:
    """Run Migration Doctor to diagnose legacy plugin state, env variables, and memory vectors."""
    return service.diagnose_migration(payload)


@router.post("/execute-migration", response_model=MigrationExecuteResponse)
async def execute_migration(
    payload: MigrationExecuteRequest,
    service: PluginGuardrailService = Depends(get_plugin_guardrail_service),
) -> MigrationExecuteResponse:
    """Execute zero-loss migration adaptation modernizing plugin config and namespacing env vars."""
    return service.execute_migration(payload)


@router.get("/history", response_model=list[PluginAuditReportResponse])
async def get_audit_history(
    limit: int = Query(default=50, ge=1, le=500),
    service: PluginGuardrailService = Depends(get_plugin_guardrail_service),
) -> list[PluginAuditReportResponse]:
    """Retrieve historical audit reports and safety ratings."""
    return service.get_audit_history(limit=limit)
