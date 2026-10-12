"""API router for Air-Gapped Sovereign Intelligence and Zero-Egress Compliance.

[INPUT]
- SetEgressTierRequest, organization_id, limit query params

[OUTPUT]
- EgressTierStatusResponse, ZeroEgressAssertionResponse, SovereignComplianceDossierResponse, list[EgressAttemptDto]

[POS]
Server API layer. Exposes REST endpoints for air-gapped sovereign intelligence and zero-egress compliance dossiers.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.air_gapped import (
    EgressAttemptDto,
    EgressTierStatusResponse,
    SetEgressTierRequest,
    SovereignComplianceDossierResponse,
    ZeroEgressAssertionResponse,
)
from app.services.security.air_gapped_service import default_air_gapped_service

router = APIRouter(prefix="/air-gapped", tags=["air-gapped"])


@router.get("/status", response_model=EgressTierStatusResponse)
async def get_egress_tier_status() -> EgressTierStatusResponse:
    """Get active egress governance tier and live telemetry."""
    return default_air_gapped_service.get_status()


@router.post("/tier", response_model=EgressTierStatusResponse)
async def set_egress_tier(
    request: SetEgressTierRequest,
) -> EgressTierStatusResponse:
    """Configure active network egress control tier (standard, conservative, air_gapped_sovereign)."""
    return default_air_gapped_service.set_tier(request)


@router.post("/assert-zero-egress", response_model=ZeroEgressAssertionResponse)
async def assert_zero_egress() -> ZeroEgressAssertionResponse:
    """Execute cryptographic zero-egress assertion proof over connection history."""
    return default_air_gapped_service.assert_zero_egress()


@router.get("/compliance-dossier", response_model=SovereignComplianceDossierResponse)
async def get_compliance_dossier(
    organization_id: str = Query(default="default_enterprise", description="Enterprise or tenant identifier"),
) -> SovereignComplianceDossierResponse:
    """Generate and export cryptographically signed sovereign compliance audit dossier."""
    return default_air_gapped_service.generate_compliance_dossier(organization_id=organization_id)


@router.get("/attempts", response_model=list[EgressAttemptDto])
async def list_egress_attempts(
    limit: int = Query(default=100, ge=1, le=1000, description="Max attempt records to return"),
) -> list[EgressAttemptDto]:
    """List recent network egress inspection attempts."""
    return default_air_gapped_service.list_attempts(limit=limit)
