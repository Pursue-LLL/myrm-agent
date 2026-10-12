"""API router for Integration Egress Trust Lifecycle.

[INPUT]
- DisconnectIntegrationRequest.

[OUTPUT]
- Endpoints for querying pre-connect disclosure cards, executing atomic disconnect
  with purge-on-disconnect guarantees, and retrieving provider revocation configs.

[POS]
- Server API. Mounted under /api/v1/security/integration-trust.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.integration_trust import (
    DisconnectIntegrationRequest,
    DisconnectIntegrationResponse,
    PreConnectDisclosureDto,
    ProviderRevokeConfigDto,
)
from app.services.security.integration_trust_service import (
    get_integration_trust_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integration-trust", tags=["integration-trust"])


@router.get("/disclosure/{provider_id}", response_model=PreConnectDisclosureDto)
def get_preconnect_disclosure(provider_id: str) -> PreConnectDisclosureDto:
    """Retrieve pre-connect disclosure card explaining data access and purge policy for provider."""
    service = get_integration_trust_service()
    disc = service.get_disclosure(provider_id)
    if disc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pre-connect disclosure card for provider '{provider_id}' not found.",
        )
    return disc


@router.get("/disclosures", response_model=list[PreConnectDisclosureDto])
def list_preconnect_disclosures() -> list[PreConnectDisclosureDto]:
    """List all registered pre-connect disclosure cards across integration providers."""
    service = get_integration_trust_service()
    return service.list_disclosures()


@router.get("/revoke-config/{provider_id}", response_model=ProviderRevokeConfigDto)
def get_provider_revoke_config(provider_id: str) -> ProviderRevokeConfigDto:
    """Retrieve token revocation capabilities and endpoints for an integration provider."""
    service = get_integration_trust_service()
    cfg = service.get_revoke_config(provider_id)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revocation configuration for provider '{provider_id}' not found.",
        )
    return cfg


@router.post("/disconnect", response_model=DisconnectIntegrationResponse)
def disconnect_integration(
    req: DisconnectIntegrationRequest,
) -> DisconnectIntegrationResponse:
    """Execute atomic disconnect: purge synced memory trees & documents, revoke OAuth token."""
    service = get_integration_trust_service()
    return service.disconnect_provider(req)
