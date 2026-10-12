"""API router for Sandbox Log Redaction and Execution Continuation Audit.

[INPUT]
- RedactLogRequest, RegisterRunRequest, HeartbeatReportRequest, ContinuationAuditRequest.

[OUTPUT]
- RedactLogResponse, RegisterRunResponse, HeartbeatReportResponse, ContinuationAuditResponse.

[POS]
- Security router mounted under /security/sandbox-log-continuation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.sandbox_log_continuation import (
    ContinuationAuditRequest,
    ContinuationAuditResponse,
    HeartbeatReportRequest,
    HeartbeatReportResponse,
    RedactLogRequest,
    RedactLogResponse,
    RegisterRunRequest,
    RegisterRunResponse,
)
from app.services.security.sandbox_log_continuation_service import (
    SandboxLogContinuationService,
    get_sandbox_log_continuation_service,
)

router = APIRouter(
    prefix="/sandbox-log-continuation", tags=["sandbox-log-continuation"]
)


@router.post("/redact", response_model=RedactLogResponse)
async def redact_sandbox_logs(
    request: RedactLogRequest,
    service: SandboxLogContinuationService = Depends(
        get_sandbox_log_continuation_service
    ),
) -> RedactLogResponse:
    """Sanitize sandbox logs and CLI commands to redact API keys and secrets."""
    return service.redact_logs(request)


@router.post("/runs", response_model=RegisterRunResponse)
async def register_execution_run(
    request: RegisterRunRequest,
    service: SandboxLogContinuationService = Depends(
        get_sandbox_log_continuation_service
    ),
) -> RegisterRunResponse:
    """Register an active execution run for audit lineage and heartbeat tracking."""
    return service.register_run(request)


@router.post("/heartbeat", response_model=HeartbeatReportResponse)
async def report_runner_heartbeat(
    request: HeartbeatReportRequest,
    service: SandboxLogContinuationService = Depends(
        get_sandbox_log_continuation_service
    ),
) -> HeartbeatReportResponse:
    """Report periodic heartbeat from an active sandbox runner."""
    return service.report_heartbeat(request)


@router.post("/audit", response_model=ContinuationAuditResponse)
async def audit_execution_continuation(
    request: ContinuationAuditRequest,
    service: SandboxLogContinuationService = Depends(
        get_sandbox_log_continuation_service
    ),
) -> ContinuationAuditResponse:
    """Audit whether an execution continuation is authoritative and not stale."""
    return service.audit_continuation(request)
