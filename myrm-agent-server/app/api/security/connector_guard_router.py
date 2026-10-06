"""FastAPI router for Connector Host Allowlist and Anti-Exfiltration SSRF Guard.

[INPUT]
- app.schemas.connector_guard::{InspectTrafficRequest, RegisterConnectorRequest, SetOutboundModeRequest, ResetCircuitBreakerRequest}
- app.services.security.connector_guard_service::{ConnectorGuardService, get_connector_guard_service}

[OUTPUT]
- router: APIRouter for connector guard traffic inspection, registry, circuit breaker, and threat alerts.

[POS]
app/api/security router exposing connector security, SSRF filtering, and outbound traffic inspection.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.connector_guard import (
    CircuitBreakerStatusResponse,
    ConnectorEntryResponse,
    InspectTrafficRequest,
    InspectTrafficResponse,
    RegisterConnectorRequest,
    ResetCircuitBreakerRequest,
    SetOutboundModeRequest,
    ThreatAlertResponse,
)
from app.services.security.connector_guard_service import (
    ConnectorGuardService,
    get_connector_guard_service,
)

router = APIRouter(prefix="/connector-guard", tags=["connector-guard"])


@router.post(
    "/inspect",
    response_model=InspectTrafficResponse,
    status_code=status.HTTP_200_OK,
    summary="Vet outbound traffic against SSRF rules and connector allowlists",
)
def inspect_traffic(
    request: InspectTrafficRequest,
    service: ConnectorGuardService = Depends(get_connector_guard_service),
) -> InspectTrafficResponse:
    """Evaluate outbound request URL, detect SSRF/exfiltration, and decide whether credentials can be injected."""
    return service.inspect_traffic(request)


@router.post(
    "/connectors",
    response_model=ConnectorEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an authorized connector endpoint allowlist",
)
def register_connector(
    request: RegisterConnectorRequest,
    service: ConnectorGuardService = Depends(get_connector_guard_service),
) -> ConnectorEntryResponse:
    """Register or update official endpoint hosts for an external connector."""
    return service.register_connector(request)


@router.get(
    "/connectors",
    response_model=list[ConnectorEntryResponse],
    summary="List registered connector allowlists",
)
def list_connectors(
    service: ConnectorGuardService = Depends(get_connector_guard_service),
) -> list[ConnectorEntryResponse]:
    """List all official connector endpoint registrations."""
    return service.list_connectors()


@router.delete(
    "/connectors/{connector_id}",
    summary="Unregister a connector from allowlist",
)
def unregister_connector(
    connector_id: str,
    service: ConnectorGuardService = Depends(get_connector_guard_service),
) -> dict[str, bool]:
    """Remove a connector from allowlist registry."""
    success = service.unregister_connector(connector_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found",
        )
    return {"success": True}


@router.get(
    "/alerts",
    response_model=list[ThreatAlertResponse],
    summary="List captured SSRF and token exfiltration alerts",
)
def get_alerts(
    session_id: str | None = Query(default=None),
    service: ConnectorGuardService = Depends(get_connector_guard_service),
) -> list[ThreatAlertResponse]:
    """Retrieve security violation alerts."""
    return service.get_alerts(session_id)


@router.post(
    "/circuit-breaker/reset",
    summary="Reset security circuit breaker for a session",
)
def reset_circuit_breaker(
    request: ResetCircuitBreakerRequest,
    service: ConnectorGuardService = Depends(get_connector_guard_service),
) -> dict[str, bool]:
    """Reset tripped circuit breaker."""
    success = service.reset_circuit_breaker(request.session_id)
    return {"success": success}


@router.get(
    "/circuit-breaker/status/{session_id}",
    response_model=CircuitBreakerStatusResponse,
    summary="Get circuit breaker status for session",
)
def get_circuit_breaker_status(
    session_id: str,
    service: ConnectorGuardService = Depends(get_connector_guard_service),
) -> CircuitBreakerStatusResponse:
    """Check if circuit breaker is currently tripped."""
    return service.get_circuit_breaker_status(session_id)


@router.post(
    "/mode",
    summary="Configure enterprise outbound policy mode",
)
def set_outbound_mode(
    request: SetOutboundModeRequest,
    service: ConnectorGuardService = Depends(get_connector_guard_service),
) -> dict[str, str]:
    """Set policy mode: strict_block_unregistered or zero_cred_permissive."""
    try:
        mode_val = service.set_outbound_mode(request.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid outbound mode: {exc}",
        ) from exc
    return {"mode": mode_val}
