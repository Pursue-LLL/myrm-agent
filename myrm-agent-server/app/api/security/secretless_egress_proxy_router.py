"""FastAPI router for Secretless Credential Egress Proxy and Placeholder Swap Suite.

[INPUT]
- app.schemas.secretless_egress_proxy::BoundCredentialRegisterRequest, InspectSwapRequest
- app.services.security.secretless_egress_proxy_service::SecretlessEgressProxyService

[OUTPUT]
- router: APIRouter for secretless credential egress proxy endpoints

[POS]
Security API surface exposing secretless credential egress proxy and placeholder swapping.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.secretless_egress_proxy import (
    BoundCredentialRegisterRequest,
    BoundCredentialResponse,
    BoundCredentialRevokeRequest,
    InspectSwapRequest,
    InspectSwapResponse,
    RevokeCredentialResponse,
    SwapEventResponse,
)
from app.services.security.secretless_egress_proxy_service import (
    SecretlessEgressProxyService,
    get_secretless_egress_proxy_service,
)

router = APIRouter(prefix="/security/secretless-egress", tags=["Security - Secretless Egress Proxy"])


@router.post("/register", response_model=BoundCredentialResponse)
async def register_credential(
    payload: BoundCredentialRegisterRequest,
    service: SecretlessEgressProxyService = Depends(get_secretless_egress_proxy_service),
) -> BoundCredentialResponse:
    """Register a real credential outside sandbox and bind a safe random placeholder to target host."""
    return service.register_credential(payload)


@router.post("/revoke", response_model=RevokeCredentialResponse)
async def revoke_credential(
    payload: BoundCredentialRevokeRequest,
    service: SecretlessEgressProxyService = Depends(get_secretless_egress_proxy_service),
) -> RevokeCredentialResponse:
    """Revoke a bound credential by target host domain."""
    return service.revoke_credential(payload.target_host)


@router.get("/credentials", response_model=list[BoundCredentialResponse])
async def list_credentials(
    service: SecretlessEgressProxyService = Depends(get_secretless_egress_proxy_service),
) -> list[BoundCredentialResponse]:
    """List all currently active bound credentials with masked placeholders."""
    return service.list_credentials()


@router.post("/inspect-swap", response_model=InspectSwapResponse)
async def inspect_and_swap(
    payload: InspectSwapRequest,
    service: SecretlessEgressProxyService = Depends(get_secretless_egress_proxy_service),
) -> InspectSwapResponse:
    """Inspect outgoing egress request and dynamically swap placeholder with real credential."""
    return service.inspect_and_swap(payload)


@router.get("/events", response_model=list[SwapEventResponse])
async def get_audit_events(
    limit: int = Query(default=50, ge=1, le=500),
    service: SecretlessEgressProxyService = Depends(get_secretless_egress_proxy_service),
) -> list[SwapEventResponse]:
    """Retrieve audit log of egress proxy inspections and placeholder swap decisions."""
    return service.get_audit_events(limit=limit)
