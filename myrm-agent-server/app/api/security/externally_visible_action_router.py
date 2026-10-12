"""FastAPI router for Externally Visible Irreversible Action Static Classification Gate.

[INPUT]
- EvaluateActionRequest, RecordExternalActionAuditRequest payloads.

[OUTPUT]
- ExternalActionClassificationResponse, AuditedExternalActionResponse, AuditTrailResponse.

[POS]
- app.api.security.externally_visible_action_router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.externally_visible_action import (
    AuditedExternalActionResponse,
    AuditTrailResponse,
    EvaluateActionRequest,
    ExternalActionClassificationResponse,
    RecordExternalActionAuditRequest,
)
from app.services.security.externally_visible_action_service import (
    ExternallyVisibleActionService,
    get_externally_visible_action_service,
)

router = APIRouter(
    prefix="/security/externally-visible-actions",
    tags=["Security - Externally Visible Action Classification & Review"],
)


@router.post("/evaluate", response_model=ExternalActionClassificationResponse)
async def evaluate_action(
    payload: EvaluateActionRequest,
    service: ExternallyVisibleActionService = Depends(get_externally_visible_action_service),
) -> ExternalActionClassificationResponse:
    """Evaluate whether an action has third-party external visibility and mandates human review."""
    return service.evaluate_action(payload)


@router.post("/record-audit", response_model=AuditedExternalActionResponse)
async def record_audit(
    payload: RecordExternalActionAuditRequest,
    service: ExternallyVisibleActionService = Depends(get_externally_visible_action_service),
) -> AuditedExternalActionResponse:
    """Record an audit trail entry for an outbound externally visible action."""
    return service.record_audit(payload)


@router.get("/audit-trail", response_model=AuditTrailResponse)
async def get_audit_trail(
    session_id: str | None = Query(default=None, description="Optional session ID filter"),
    limit: int = Query(default=50, ge=1, le=500, description="Max audit entries to retrieve"),
    service: ExternallyVisibleActionService = Depends(get_externally_visible_action_service),
) -> AuditTrailResponse:
    """Query recent external action audit records."""
    return service.get_audit_trail(session_id=session_id, limit=limit)
