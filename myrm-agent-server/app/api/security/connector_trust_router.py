"""FastAPI router for Connector Catalog Trust Grading and Server Review Provenance.

[INPUT]
- REST requests for connector trust profile, preflight check, continuous review, and disclosure.

[OUTPUT]
- CatalogTrustProfileResponse, InstallationPreflightResponse, ContinuousReviewReportResponse.

[POS]
- app.api.security.connector_trust_router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.connector_trust import (
    CatalogTrustProfileResponse,
    ContinuousReviewReportResponse,
    InstallationPreflightRequest,
    InstallationPreflightResponse,
    UnreviewedDisclosureResponse,
)
from app.services.security.connector_trust_service import (
    ConnectorTrustService,
    get_connector_trust_service,
)

router = APIRouter(
    prefix="/security/connector-trust",
    tags=["Security - Connector Catalog Trust & Review Provenance"],
)


@router.get("/profiles", response_model=list[CatalogTrustProfileResponse])
async def list_trust_profiles(
    service: ConnectorTrustService = Depends(get_connector_trust_service),
) -> list[CatalogTrustProfileResponse]:
    """List all verified and reviewed connector trust classification profiles."""
    return service.list_trust_profiles()


@router.get("/profiles/{connector_id}", response_model=CatalogTrustProfileResponse)
async def get_trust_profile(
    connector_id: str,
    service: ConnectorTrustService = Depends(get_connector_trust_service),
) -> CatalogTrustProfileResponse:
    """Retrieve security audit review and capability surface profile for a connector."""
    return service.get_trust_profile(connector_id)


@router.post("/preflight", response_model=InstallationPreflightResponse)
async def evaluate_preflight(
    payload: InstallationPreflightRequest,
    service: ConnectorTrustService = Depends(get_connector_trust_service),
) -> InstallationPreflightResponse:
    """Run pre-installation security verification, provenance check, and least-privilege scoping."""
    return service.evaluate_installation_preflight(payload)


@router.post("/continuous-review", response_model=ContinuousReviewReportResponse)
async def perform_continuous_review(
    service: ConnectorTrustService = Depends(get_connector_trust_service),
) -> ContinuousReviewReportResponse:
    """Perform periodic continuous review scanning for audit expirations and version provenance drift."""
    return service.perform_continuous_review()


@router.get(
    "/unreviewed-disclosure/{connector_id}",
    response_model=UnreviewedDisclosureResponse,
)
async def get_unreviewed_disclosure(
    connector_id: str,
    service: ConnectorTrustService = Depends(get_connector_trust_service),
) -> UnreviewedDisclosureResponse:
    """Get honest risk disclosure and required acknowledgement prompt for unreviewed connectors."""
    return service.get_unreviewed_disclosure(connector_id)
