"""API router for Dual-Tier Root Admin & User API Key Isolation Suite.

[INPUT]
- RegisterAdminKeyRequest, DeriveUserKeyRequest, EvaluateAccessRequest payloads.

[OUTPUT]
- RegisterAdminKeyResponseDto, DeriveUserKeyResponseDto, EvaluateAccessResponseDto.

[POS]
- Security router mounted under /security/dual-tier-isolation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.dual_tier_isolation import (
    DeriveUserKeyRequest,
    DeriveUserKeyResponseDto,
    EvaluateAccessRequest,
    EvaluateAccessResponseDto,
    RegisterAdminKeyRequest,
    RegisterAdminKeyResponseDto,
)
from app.services.security.dual_tier_isolation_service import (
    DualTierIsolationService,
    get_dual_tier_isolation_service,
)

router = APIRouter(prefix="/dual-tier-isolation", tags=["dual-tier-isolation"])


@router.post("/register-admin-key", response_model=RegisterAdminKeyResponseDto)
async def register_admin_key(
    request: RegisterAdminKeyRequest,
    service: DualTierIsolationService = Depends(get_dual_tier_isolation_service),
) -> RegisterAdminKeyResponseDto:
    """Register Root Admin key for control-plane management."""
    return service.register_admin_key(request)


@router.post("/derive-user-key", response_model=DeriveUserKeyResponseDto)
async def derive_user_key(
    request: DeriveUserKeyRequest,
    service: DualTierIsolationService = Depends(get_dual_tier_isolation_service),
) -> DeriveUserKeyResponseDto:
    """Derive isolated User API key bound to specific user/tenant context."""
    return service.derive_user_key(request)


@router.post("/evaluate-access", response_model=EvaluateAccessResponseDto)
async def evaluate_access(
    request: EvaluateAccessRequest,
    service: DualTierIsolationService = Depends(get_dual_tier_isolation_service),
) -> EvaluateAccessResponseDto:
    """Evaluate operation against dual-tier physical control/data plane boundary."""
    return service.evaluate_access(request)
