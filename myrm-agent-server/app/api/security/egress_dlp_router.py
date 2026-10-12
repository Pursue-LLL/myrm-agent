"""API router for Agent Egress Telemetry Scraper & Enterprise DLP Guard.

[INPUT]
- ValidateEgressPolicyRequest, ScanDependenciesRequest, ScanProjectRequest.

[OUTPUT]
- Endpoints for egress network policy validation, dependency manifest scanning,
  codebase inspection, and signature catalog queries.

[POS]
- Server API. Mounted under /api/v1/security/egress-dlp.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.egress_dlp import (
    DLPScanResultDto,
    ScanDependenciesRequest,
    ScanProjectRequest,
    TelemetrySignatureDto,
    ValidateEgressPolicyRequest,
)
from app.services.security.egress_dlp_service import get_egress_dlp_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/egress-dlp", tags=["egress-dlp"])


@router.post("/validate-policy", response_model=DLPScanResultDto)
def validate_egress_policy(request: ValidateEgressPolicyRequest) -> DLPScanResultDto:
    """Validate declared egress network rules against enterprise telemetry blacklists."""
    service = get_egress_dlp_service()
    return service.validate_egress_rules(request)


@router.post("/scan-dependencies", response_model=DLPScanResultDto)
def scan_dependencies(request: ScanDependenciesRequest) -> DLPScanResultDto:
    """Scan dependency manifest content (requirements.txt, etc.) for telemetry tracking libraries."""
    service = get_egress_dlp_service()
    return service.scan_dependencies(request)


@router.post("/scan-project", response_model=DLPScanResultDto)
def scan_project(request: ScanProjectRequest) -> DLPScanResultDto:
    """Inspect local project directory files for hardcoded telemetry domains or imports."""
    service = get_egress_dlp_service()
    return service.scan_project(request)


@router.get("/signatures", response_model=list[TelemetrySignatureDto])
def list_telemetry_signatures() -> list[TelemetrySignatureDto]:
    """Retrieve catalog of pre-compiled third-party telemetry domain signatures."""
    service = get_egress_dlp_service()
    return service.list_signatures()
