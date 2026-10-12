"""API router for Tripartite Isolation & Immutable Audit Ledger.

[INPUT]
- AppendAuditRecordRequest, AuditQueryRequest, ActionSemanticExecutionRequest,
  OpsRegisterTaskRequest, OpsForceStopRequest.

[OUTPUT]
- Endpoints for Layer-3 audit recording, cryptographic verification,
  action semantics execution, and zero-knowledge ops control.

[POS]
- Server API. Mounted under /api/v1/security/tripartite-ledger.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.core.security.tripartite_ledger import (
    ActionSemanticViolationError,
    AuditIntegrityError,
    PreIOAuditAssertionError,
)

from app.schemas.tripartite_ledger import (
    ActionSemanticExecutionRequest,
    ActionSemanticExecutionResponse,
    AppendAuditRecordRequest,
    AuditEvidenceRecordDto,
    AuditQueryRequest,
    AuditQueryResponse,
    OpsForceStopRequest,
    OpsForceStopResponse,
    OpsRegisterTaskRequest,
    OpsTelemetryDto,
    VerifyLedgerResponse,
)
from app.services.security.tripartite_ledger_service import (
    get_tripartite_ledger_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tripartite-ledger", tags=["tripartite-ledger"])


@router.post("/records", response_model=AuditEvidenceRecordDto, status_code=status.HTTP_201_CREATED)
def append_audit_record(req: AppendAuditRecordRequest) -> AuditEvidenceRecordDto:
    """Commit an immutable audit evidence record to the cryptographic ledger."""
    service = get_tripartite_ledger_service()
    try:
        return service.append_record(req)
    except AuditIntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/verify", response_model=VerifyLedgerResponse)
def verify_audit_ledger() -> VerifyLedgerResponse:
    """Verify the integrity of the immutable audit ledger cryptographic hash chain."""
    service = get_tripartite_ledger_service()
    return service.verify_ledger()


@router.post("/query", response_model=AuditQueryResponse)
def query_audit_records(req: AuditQueryRequest) -> AuditQueryResponse:
    """Query immutable audit records by source, tool, agent, or time window."""
    service = get_tripartite_ledger_service()
    return service.query_records(req)


@router.post("/execute", response_model=ActionSemanticExecutionResponse)
def execute_semantic_action(req: ActionSemanticExecutionRequest) -> ActionSemanticExecutionResponse:
    """Execute action under semantic boundaries (REPLAY_LOG, OFFLINE_EVAL, RE_EXECUTE)."""
    service = get_tripartite_ledger_service()
    try:
        return service.execute_semantic_action(req)
    except PreIOAuditAssertionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ActionSemanticViolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/ops/tasks", response_model=OpsTelemetryDto, status_code=status.HTTP_201_CREATED)
def register_ops_task(req: OpsRegisterTaskRequest) -> OpsTelemetryDto:
    """Register task for zero-knowledge operational tracking."""
    service = get_tripartite_ledger_service()
    return service.register_task(req)


@router.get("/ops/telemetry/{task_id}", response_model=OpsTelemetryDto)
def get_ops_telemetry(task_id: str) -> OpsTelemetryDto:
    """Get operational telemetry strictly without prompt or conversation contents."""
    service = get_tripartite_ledger_service()
    return service.get_ops_telemetry(task_id)


@router.post("/ops/force-stop", response_model=OpsForceStopResponse)
def ops_force_stop(req: OpsForceStopRequest) -> OpsForceStopResponse:
    """Terminate task via ops control without access to task business contents."""
    service = get_tripartite_ledger_service()
    return service.ops_force_stop(req)
