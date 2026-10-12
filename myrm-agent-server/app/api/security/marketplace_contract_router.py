"""API router for Marketplace Manifest Source Pinning & Capability Contract.

[INPUT]
- ValidateManifestRequest, EvaluateAdmissionRequest, UpdateAdmissionPolicyRequest.

[OUTPUT]
- Endpoints for validating manifest source pinning and capability declarations,
  evaluating organization admission allowlists, and managing admission policies.

[POS]
- Server API. Mounted under /api/v1/security/marketplace-contract.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.marketplace_contract import (
    AdmissionPolicyDto,
    EvaluateAdmissionRequest,
    EvaluateAdmissionResponse,
    UpdateAdmissionPolicyRequest,
    ValidateManifestRequest,
    ValidateManifestResponse,
)
from app.services.security.marketplace_contract_service import (
    get_marketplace_contract_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketplace-contract", tags=["marketplace-contract"])


@router.post("/validate", response_model=ValidateManifestResponse)
def validate_manifest(req: ValidateManifestRequest) -> ValidateManifestResponse:
    """Validate package manifest source pinning, immutable SHA format, and platform support."""
    service = get_marketplace_contract_service()
    return service.validate_manifest(req)


@router.post("/evaluate", response_model=EvaluateAdmissionResponse)
def evaluate_admission(req: EvaluateAdmissionRequest) -> EvaluateAdmissionResponse:
    """Evaluate package manifest against active organization admission allowlists and capability restrictions."""
    service = get_marketplace_contract_service()
    return service.evaluate_admission(req)


@router.get("/policy", response_model=AdmissionPolicyDto)
def get_admission_policy() -> AdmissionPolicyDto:
    """Retrieve active organization admission policy."""
    service = get_marketplace_contract_service()
    return service.get_policy()


@router.put("/policy", response_model=AdmissionPolicyDto)
def update_admission_policy(req: UpdateAdmissionPolicyRequest) -> AdmissionPolicyDto:
    """Update organization admission allowlists and capability restrictions."""
    service = get_marketplace_contract_service()
    return service.update_policy(req)
