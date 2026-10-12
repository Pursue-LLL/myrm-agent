"""
[POS] app/api/security/outbound_ebrake_mesh_router.py
[INPUT] fastapi, app.schemas.outbound_ebrake_mesh, app.services.security.outbound_ebrake_mesh_service
[OUTPUT] outbound_ebrake_mesh_router

REST API router for Outbound Irreversible Action E-Brake & Privacy-Preserving Chief of Staff Mesh Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.outbound_ebrake_mesh import (
    CalendarNegotiationResponseDTO,
    CancelOutboundActionRequestDTO,
    EBrakeStatusResponseDTO,
    EnqueueOutboundActionRequestDTO,
    GhostInspectionVerdictResponseDTO,
    InspectOutboundActionRequestDTO,
    NegotiateCalendarRequestDTO,
    OutboundActionItemResponseDTO,
    OutboundEBrakeMetricsResponseDTO,
    TriggerEBrakeRequestDTO,
)
from app.services.security.outbound_ebrake_mesh_service import (
    OutboundEBrakeMeshService,
    get_outbound_ebrake_mesh_service,
)

router = APIRouter(
    prefix="/outbound-ebrake-mesh",
    tags=["Outbound E-Brake & Chief of Staff Mesh"],
)


@router.post(
    "/inspect",
    response_model=GhostInspectionVerdictResponseDTO,
    summary="Inspect outbound action",
)
def inspect_outbound_action(
    request: InspectOutboundActionRequestDTO,
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> GhostInspectionVerdictResponseDTO:
    """Perform pre-flight ghost inspection evaluating audience boundaries and token leak risks."""
    return service.inspect_outbound_action(request)


@router.post(
    "/actions/enqueue",
    response_model=OutboundActionItemResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue outbound action",
)
def enqueue_action(
    request: EnqueueOutboundActionRequestDTO,
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> OutboundActionItemResponseDTO:
    """Enqueue inspected outbound action into grace cooldown buffer."""
    return service.enqueue_action(request)


@router.post(
    "/actions/{action_id}/cancel",
    response_model=dict[str, bool],
    summary="Cancel queued action",
)
def cancel_action(
    action_id: str,
    request: CancelOutboundActionRequestDTO,
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> dict[str, bool]:
    """Explicitly cancel a pending action during cooldown countdown."""
    cancelled = service.cancel_action(action_id, request)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found or not in queued cooldown state",
        )
    return {"cancelled": True}


@router.post(
    "/actions/{action_id}/flush",
    response_model=dict[str, bool],
    summary="Flush action immediately",
)
def flush_action(
    action_id: str,
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> dict[str, bool]:
    """Bypass remaining cooldown and dispatch action immediately."""
    flushed = service.flush_action(action_id)
    if not flushed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found or not in queued cooldown state",
        )
    return {"flushed": True}


@router.get(
    "/actions/queued",
    response_model=list[OutboundActionItemResponseDTO],
    summary="List queued actions",
)
def list_queued_actions(
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> list[OutboundActionItemResponseDTO]:
    """List all actions currently waiting in the grace-period cooldown buffer."""
    return service.list_queued_actions()


@router.get(
    "/actions/{action_id}",
    response_model=OutboundActionItemResponseDTO,
    summary="Get action item",
)
def get_action(
    action_id: str,
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> OutboundActionItemResponseDTO:
    """Retrieve buffered action details by action ID."""
    item = service.get_action(action_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found",
        )
    return item


@router.post(
    "/actions/poll-dispatch",
    response_model=list[OutboundActionItemResponseDTO],
    summary="Poll and dispatch expired actions",
)
def poll_and_dispatch(
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> list[OutboundActionItemResponseDTO]:
    """Poll and dispatch actions whose cooldown timer has expired."""
    return service.poll_and_dispatch()


@router.post(
    "/ebrake/trigger",
    response_model=dict[str, int],
    summary="Trigger emergency physical brake",
)
def trigger_e_brake(
    request: TriggerEBrakeRequestDTO,
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> dict[str, int]:
    """Immediately abort and purge all pending outbound actions via emergency brake."""
    aborted_count = service.trigger_e_brake(request)
    return {"aborted_actions_count": aborted_count}


@router.post(
    "/ebrake/reset",
    response_model=dict[str, bool],
    summary="Reset emergency brake",
)
def reset_e_brake(
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> dict[str, bool]:
    """Reset emergency brake to resume normal queuing."""
    return {"reset": service.reset_e_brake()}


@router.get(
    "/ebrake/status",
    response_model=EBrakeStatusResponseDTO,
    summary="Get emergency brake status",
)
def get_e_brake_status(
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> EBrakeStatusResponseDTO:
    """Retrieve current emergency brake state snapshot."""
    return service.get_e_brake_status()


@router.post(
    "/calendar/negotiate",
    response_model=CalendarNegotiationResponseDTO,
    summary="Negotiate calendar scheduling via A2A mesh",
)
def negotiate_calendar(
    request: NegotiateCalendarRequestDTO,
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> CalendarNegotiationResponseDTO:
    """Execute zero-knowledge privacy-preserving calendar negotiation between agents."""
    return service.negotiate_calendar(request)


@router.get(
    "/metrics",
    response_model=OutboundEBrakeMetricsResponseDTO,
    summary="Get operational metrics",
)
def get_metrics(
    service: OutboundEBrakeMeshService = Depends(get_outbound_ebrake_mesh_service),
) -> OutboundEBrakeMetricsResponseDTO:
    """Retrieve cumulative operational metrics for outbound gate, e-brake, and calendar mesh."""
    return service.get_metrics()
