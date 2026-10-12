"""API router for Inherited Identity Protection and Session Resume Guard.

[INPUT]
- SanitizeEnvRequest, ResolveSessionRefRequest, CreateResumePlanRequest.

[OUTPUT]
- SanitizeEnvResponse, ResolveSessionRefResponse, CreateResumePlanResponse.

[POS]
- Security router mounted under /security/inherited-identity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.inherited_identity_guard import (
    CreateResumePlanRequest,
    CreateResumePlanResponse,
    ResolveSessionRefRequest,
    ResolveSessionRefResponse,
    SanitizeEnvRequest,
    SanitizeEnvResponse,
)
from app.services.security.inherited_identity_guard_service import (
    InheritedIdentityGuardService,
    inherited_identity_guard_service,
)

router = APIRouter(
    prefix="/inherited-identity", tags=["inherited-identity-guard"]
)


def get_inherited_identity_guard_service() -> InheritedIdentityGuardService:
    """Dependency provider for InheritedIdentityGuardService."""
    return inherited_identity_guard_service


@router.post(
    "/sanitize-env",
    response_model=SanitizeEnvResponse,
    status_code=status.HTTP_200_OK,
)
async def sanitize_environment(
    request: SanitizeEnvRequest,
    service: InheritedIdentityGuardService = Depends(
        get_inherited_identity_guard_service
    ),
) -> SanitizeEnvResponse:
    """Strip inherited terminal and agent session identifiers to guarantee isolation."""
    try:
        return service.sanitize_environment(request)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Environment sanitization failed: {exc}",
        ) from exc


@router.post(
    "/resolve-session-ref",
    response_model=ResolveSessionRefResponse,
    status_code=status.HTTP_200_OK,
)
async def resolve_session_reference(
    request: ResolveSessionRefRequest,
    service: InheritedIdentityGuardService = Depends(
        get_inherited_identity_guard_service
    ),
) -> ResolveSessionRefResponse:
    """Parse and validate an agent session reference against registered official origins."""
    return service.resolve_session_reference(request)


@router.post(
    "/create-resume-plan",
    response_model=CreateResumePlanResponse,
    status_code=status.HTTP_200_OK,
)
async def create_resume_plan(
    request: CreateResumePlanRequest,
    service: InheritedIdentityGuardService = Depends(
        get_inherited_identity_guard_service
    ),
) -> CreateResumePlanResponse:
    """Validate origin and derive command arguments for official agent resumption."""
    return service.generate_resume_plan(request)
