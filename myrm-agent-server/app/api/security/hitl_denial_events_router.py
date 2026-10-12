"""FastAPI router for Human-in-the-Loop (HITL) denial events and workflow control.

[INPUT]
- ProcessHitlDecisionsRequest JSON payloads.

[OUTPUT]
- ProcessHitlDecisionsResponse and HitlPoliciesConfigResponse JSON payloads.

[POS]
- REST API layer exposing HITL denial event dispatching and policy queries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.hitl_denial_events import (
    HitlPoliciesConfigResponse,
    ProcessHitlDecisionsRequest,
    ProcessHitlDecisionsResponse,
)
from app.services.security.hitl_denial_events_service import (
    HitlDenialEventsService,
    get_hitl_denial_events_service,
)

router = APIRouter(
    prefix="/hitl-denials",
    tags=["Security: HITL Denial Events"],
)


@router.post(
    "/process",
    response_model=ProcessHitlDecisionsResponse,
    summary="Process human-in-the-loop decisions and emit tool result events",
)
def process_hitl_decisions(
    request: ProcessHitlDecisionsRequest,
    service: HitlDenialEventsService = Depends(get_hitl_denial_events_service),
) -> ProcessHitlDecisionsResponse:
    """Process confirmation decisions, ensuring explicit events on denial."""
    return service.process_decisions(request)


@router.get(
    "/policies",
    response_model=HitlPoliciesConfigResponse,
    summary="Get available all-tools-denied policies and configuration",
)
def get_policies_config(
    service: HitlDenialEventsService = Depends(get_hitl_denial_events_service),
) -> HitlPoliciesConfigResponse:
    """Return available policies and default execution parameters."""
    return service.get_policies_config()
