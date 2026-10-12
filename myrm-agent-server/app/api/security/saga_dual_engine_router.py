"""API router for Spatiotemporal Duality, Connector Trust & Declarative Saga.

[INPUT]
- GrantTrustLeaseRequest, RevokeTrustLeaseRequest, ExecuteDualToolRequest.

[OUTPUT]
- Endpoints for granting connector trust, executing dual tools with gates,
  triggering Saga rollback, and retrieving immutable emission audit logs.

[POS]
- Server API. Mounted under /api/v1/security/saga-dual-engine.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.core.security.saga_dual_engine import (
    ConnectorUntrustedError,
    EmissionUnconfirmedError,
    SagaRollbackError,
)

from app.schemas.saga_dual_engine import (
    ConnectorTrustLeaseDto,
    EmissionAuditRecordDto,
    ExecuteDualToolRequest,
    ExecuteDualToolResponse,
    GrantTrustLeaseRequest,
    RevokeTrustLeaseRequest,
    RevokeTrustLeaseResponse,
    SagaRollbackResponse,
)
from app.services.security.saga_dual_engine_service import (
    get_saga_dual_engine_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/saga-dual-engine", tags=["saga-dual-engine"])


@router.post("/leases", response_model=ConnectorTrustLeaseDto, status_code=status.HTTP_201_CREATED)
def grant_connector_trust_lease(req: GrantTrustLeaseRequest) -> ConnectorTrustLeaseDto:
    """Grant an explicit trust authorization lease to an external connector."""
    service = get_saga_dual_engine_service()
    return service.grant_lease(req)


@router.post("/leases/revoke", response_model=RevokeTrustLeaseResponse)
def revoke_connector_trust_lease(req: RevokeTrustLeaseRequest) -> RevokeTrustLeaseResponse:
    """Revoke an active connector trust authorization lease."""
    service = get_saga_dual_engine_service()
    return service.revoke_lease(req)


@router.post("/execute", response_model=ExecuteDualToolResponse)
def execute_dual_tool(req: ExecuteDualToolRequest) -> ExecuteDualToolResponse:
    """Execute a tool respecting Acquisition vs Emission duality, connector trust, and HITL."""
    service = get_saga_dual_engine_service()
    try:
        return service.execute_tool(req)
    except ConnectorUntrustedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EmissionUnconfirmedError as exc:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/rollback", response_model=SagaRollbackResponse)
def trigger_saga_rollback() -> SagaRollbackResponse:
    """Trigger reverse LIFO declarative Saga rollback for executed emission steps."""
    service = get_saga_dual_engine_service()
    try:
        return service.rollback_saga()
    except SagaRollbackError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/audit-log", response_model=list[EmissionAuditRecordDto])
def get_emission_audit_log() -> list[EmissionAuditRecordDto]:
    """Retrieve full immutable emission audit trail."""
    service = get_saga_dual_engine_service()
    return service.get_audit_log()
