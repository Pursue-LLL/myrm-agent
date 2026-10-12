"""API router for Third-Party Asset License Compliance & Copyleft Gating.

[INPUT]
- EvaluateLicenseRequest, RegisterAssetRequest.

[OUTPUT]
- Endpoints for pre-install license evaluation, asset inventory management,
  aggregated compliance summaries, and CycloneDX SBOM exports.

[POS]
- Server API. Mounted under /api/v1/security/license-compliance.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.license_compliance import (
    AssetLicenseDescriptorDto,
    CycloneDxLicenseRecordDto,
    EvaluateLicenseRequest,
    EvaluateLicenseResponse,
    LicenseInventorySummaryDto,
    RegisterAssetRequest,
)
from app.services.security.license_compliance_service import (
    get_license_compliance_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/license-compliance", tags=["license-compliance"])


@router.post("/evaluate", response_model=EvaluateLicenseResponse)
def evaluate_asset_license(request: EvaluateLicenseRequest) -> EvaluateLicenseResponse:
    """Preflight evaluate third-party asset license against deployment gating policies."""
    service = get_license_compliance_service()
    return service.evaluate_asset(request)


@router.post("/assets", response_model=AssetLicenseDescriptorDto, status_code=status.HTTP_201_CREATED)
def register_asset(request: RegisterAssetRequest) -> AssetLicenseDescriptorDto:
    """Register and scan a third-party asset into the compliance inventory ledger."""
    service = get_license_compliance_service()
    return service.register_asset(request)


@router.get("/assets", response_model=list[AssetLicenseDescriptorDto])
def list_assets() -> list[AssetLicenseDescriptorDto]:
    """List all currently tracked third-party assets in the inventory ledger."""
    service = get_license_compliance_service()
    return service.list_assets()


@router.delete("/assets/{asset_id}")
def unregister_asset(asset_id: str) -> dict[str, bool]:
    """Remove a third-party asset from the compliance inventory ledger."""
    service = get_license_compliance_service()
    success = service.unregister_asset(asset_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found in compliance ledger.",
        )
    return {"success": True}


@router.get("/summary", response_model=LicenseInventorySummaryDto)
def get_inventory_summary(
    environment: str = Query(
        default="CLOUD_COMMERCIAL",
        description="Target deployment environment: CLOUD_COMMERCIAL or LOCAL_DESKTOP",
    ),
) -> LicenseInventorySummaryDto:
    """Generate aggregated compliance summary and risk breakdown across all tracked assets."""
    service = get_license_compliance_service()
    return service.get_inventory_summary(environment=environment)


@router.get("/export/cyclonedx", response_model=list[CycloneDxLicenseRecordDto])
def export_cyclonedx_sbom() -> list[CycloneDxLicenseRecordDto]:
    """Export tracked third-party asset licenses formatted as CycloneDX SBOM records."""
    service = get_license_compliance_service()
    return service.export_cyclonedx_sbom()
