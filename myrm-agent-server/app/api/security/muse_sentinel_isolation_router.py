"""FastAPI router for Muse-Style Secure VM Isolation and Sentinel Suite.

[INPUT]
- HTTP requests via FastAPI for secure VM lifecycle, ephemeral tokens, and outbound traffic review.

[OUTPUT]
- APIRouter exposing endpoints for sandbox VM isolation and sentinel traffic inspection.

[POS]
API presentation layer for muse sentinel isolation governance.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.muse_sentinel_isolation import (
    IssueSingleUseTokenRequest,
    RedeemSingleUseTokenRequest,
    RegisterVmRequest,
    ReviewOutboundTrafficRequest,
    SecureVmProfileResponse,
    SentinelReviewResultResponse,
    SingleUseTokenResponse,
    TokenRedemptionResultResponse,
)
from app.services.security.muse_sentinel_isolation_service import (
    MuseSentinelIsolationService,
    get_muse_sentinel_isolation_service,
)

router = APIRouter(prefix="/muse-sentinel-isolation", tags=["muse-sentinel-isolation"])


@router.post(
    "/vms",
    response_model=SecureVmProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register or provision a user-dedicated secure sandbox VM",
)
def register_vm(
    request: RegisterVmRequest,
    service: MuseSentinelIsolationService = Depends(get_muse_sentinel_isolation_service),
) -> SecureVmProfileResponse:
    """Provision a dedicated sandbox environment isolating agent execution and persistent data."""
    try:
        return service.register_vm(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid isolation tier: {exc}",
        ) from exc


@router.get(
    "/vms/{vm_id}",
    response_model=SecureVmProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get secure VM descriptor by vm_id",
)
def get_vm(
    vm_id: str,
    service: MuseSentinelIsolationService = Depends(get_muse_sentinel_isolation_service),
) -> SecureVmProfileResponse:
    """Retrieve details of a registered VM environment."""
    profile = service.get_vm(vm_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Secure VM '{vm_id}' not found.",
        )
    return profile


@router.get(
    "/vms/user/{user_id}",
    response_model=SecureVmProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get secure VM descriptor by user_id",
)
def get_user_vm(
    user_id: str,
    service: MuseSentinelIsolationService = Depends(get_muse_sentinel_isolation_service),
) -> SecureVmProfileResponse:
    """Retrieve dedicated VM associated with a specific user."""
    profile = service.get_user_vm(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No secure VM found for user '{user_id}'.",
        )
    return profile


@router.get(
    "/vms",
    response_model=list[SecureVmProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="List all registered secure VM descriptors",
)
def list_vms(
    service: MuseSentinelIsolationService = Depends(get_muse_sentinel_isolation_service),
) -> list[SecureVmProfileResponse]:
    """List all active dedicated VM descriptors."""
    return service.list_vms()


@router.post(
    "/sentinel/review",
    response_model=SentinelReviewResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Screen outbound network traffic frame before leaving sandbox",
)
def review_outbound(
    request: ReviewOutboundTrafficRequest,
    service: MuseSentinelIsolationService = Depends(get_muse_sentinel_isolation_service),
) -> SentinelReviewResultResponse:
    """Evaluate egress traffic frame for credential leakage or exfiltration attempts."""
    return service.review_outbound(request)


@router.post(
    "/tokens",
    response_model=SingleUseTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint a single-use virtual token or ephemeral card",
)
def issue_single_use_token(
    request: IssueSingleUseTokenRequest,
    service: MuseSentinelIsolationService = Depends(get_muse_sentinel_isolation_service),
) -> SingleUseTokenResponse:
    """Issue a bounded one-time credential preventing exposure of real payment secrets."""
    try:
        return service.issue_single_use_token(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid token parameters: {exc}",
        ) from exc


@router.post(
    "/tokens/redeem",
    response_model=TokenRedemptionResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Redeem and burn a single-use credential",
)
def redeem_single_use_token(
    request: RedeemSingleUseTokenRequest,
    service: MuseSentinelIsolationService = Depends(get_muse_sentinel_isolation_service),
) -> TokenRedemptionResultResponse:
    """Validate and consume a single-use token, enforcing budget ceiling and recipient bounds."""
    return service.redeem_single_use_token(request)


@router.get(
    "/tokens",
    response_model=list[SingleUseTokenResponse],
    status_code=status.HTTP_200_OK,
    summary="List active unconsumed single-use tokens",
)
def list_active_tokens(
    service: MuseSentinelIsolationService = Depends(get_muse_sentinel_isolation_service),
) -> list[SingleUseTokenResponse]:
    """Retrieve all unexpired, unconsumed single-use credentials."""
    return service.list_active_tokens()
