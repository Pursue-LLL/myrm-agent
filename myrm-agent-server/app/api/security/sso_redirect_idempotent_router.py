"""API router for SSO Redirect Idempotence and Probe Hysteresis.

[INPUT]
- BuildSsoRedirectRequest, ValidateNavigationTargetRequest, RecordProbeRequest.

[OUTPUT]
- BuildSsoRedirectResponse, ValidateNavigationTargetResponse, RecordProbeResponse.

[POS]
- Security router mounted under /security/sso-redirect-idempotent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.sso_redirect_idempotent import (
    BuildSsoRedirectRequest,
    BuildSsoRedirectResponse,
    RecordProbeRequest,
    RecordProbeResponse,
    ValidateNavigationTargetRequest,
    ValidateNavigationTargetResponse,
)
from app.services.security.sso_redirect_idempotent_service import (
    SsoRedirectIdempotentService,
    get_sso_redirect_idempotent_service,
)

router = APIRouter(
    prefix="/sso-redirect-idempotent", tags=["sso-redirect-idempotent"]
)


@router.post(
    "/build-redirect-url",
    response_model=BuildSsoRedirectResponse,
    status_code=status.HTTP_200_OK,
)
async def build_sso_redirect_url(
    request: BuildSsoRedirectRequest,
    service: SsoRedirectIdempotentService = Depends(
        get_sso_redirect_idempotent_service
    ),
) -> BuildSsoRedirectResponse:
    """Build idempotent SSO redirect URL, purging stale authorization codes."""
    return service.build_redirect_url(request)


@router.post(
    "/validate-navigation-target",
    response_model=ValidateNavigationTargetResponse,
    status_code=status.HTTP_200_OK,
)
async def validate_navigation_target(
    request: ValidateNavigationTargetRequest,
    service: SsoRedirectIdempotentService = Depends(
        get_sso_redirect_idempotent_service
    ),
) -> ValidateNavigationTargetResponse:
    """Validate destination safety against open redirect attacks."""
    return service.validate_navigation_target(request)


@router.post(
    "/record-probe",
    response_model=RecordProbeResponse,
    status_code=status.HTTP_200_OK,
)
async def record_probe(
    request: RecordProbeRequest,
    service: SsoRedirectIdempotentService = Depends(
        get_sso_redirect_idempotent_service
    ),
) -> RecordProbeResponse:
    """Record network health probe and update hysteresis dampening state."""
    return service.record_probe(request)
