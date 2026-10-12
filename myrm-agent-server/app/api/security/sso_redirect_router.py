"""API router for SSO Redirect Idempotency and Probe Hysteresis.

[INPUT]
- ValidateRedirectTargetRequest, BuildSsoRedirectUrlRequest, EvaluateProbeRequest.

[OUTPUT]
- ValidateRedirectTargetResponse, BuildSsoRedirectUrlResponse, EvaluateProbeResponse.

[POS]
- Security router mounted under /security/sso-redirect.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.sso_redirect import (
    BuildSsoRedirectUrlRequest,
    BuildSsoRedirectUrlResponse,
    EvaluateProbeRequest,
    EvaluateProbeResponse,
    ValidateRedirectTargetRequest,
    ValidateRedirectTargetResponse,
)
from app.services.security.sso_redirect_service import SsoRedirectService

router = APIRouter(prefix="/sso-redirect", tags=["sso-redirect"])

_default_service = SsoRedirectService()


def get_sso_redirect_service() -> SsoRedirectService:
    """Dependency provider for SsoRedirectService."""
    return _default_service


@router.post(
    "/validate-target",
    response_model=ValidateRedirectTargetResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate redirect URL against open-redirect attacks",
)
async def validate_redirect_target(
    request: ValidateRedirectTargetRequest,
    service: SsoRedirectService = Depends(get_sso_redirect_service),
) -> ValidateRedirectTargetResponse:
    """Validate whether target URL represents a safe relative path or allowed absolute host."""
    return service.validate_target(request)


@router.post(
    "/build-url",
    response_model=BuildSsoRedirectUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Construct idempotent SSO redirect URL with stripped legacy codes",
)
async def build_sso_redirect_url(
    request: BuildSsoRedirectUrlRequest,
    service: SsoRedirectService = Depends(get_sso_redirect_service),
) -> BuildSsoRedirectUrlResponse:
    """Strip legacy authorization code query params and append a fresh code idempotently."""
    return service.build_redirect_url(request)


@router.post(
    "/evaluate-probe",
    response_model=EvaluateProbeResponse,
    status_code=status.HTTP_200_OK,
    summary="Record health/connection probe result and evaluate hysteresis",
)
async def evaluate_probe(
    request: EvaluateProbeRequest,
    service: SsoRedirectService = Depends(get_sso_redirect_service),
) -> EvaluateProbeResponse:
    """Track consecutive probe successes and failures to prevent UI toggling between states."""
    return service.evaluate_probe(request)
