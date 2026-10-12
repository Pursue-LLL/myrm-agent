"""FastAPI router for Admin Authentication Surface management.

[INPUT]
- app.services.security.admin_auth_surface_service::AdminAuthSurfaceService (POS: Manages authentication surface configuration)

[OUTPUT]
- APIRouter handling /admin-auth-surface endpoints for get, validate, and update.

[POS]
REST API layer exposing unified admin authentication surface governance and anti-lockout security.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.admin_auth_surface import (
    AdminAuthSurfaceConfigDto,
    AuthSurfaceValidationResultDto,
    UpdateAuthSurfaceRequest,
    UpdateAuthSurfaceResponse,
)
from app.services.security.admin_auth_surface_service import (
    AdminAuthSurfaceService,
    get_admin_auth_surface_service,
)

router = APIRouter(
    prefix="/admin-auth-surface",
    tags=["Security: Admin Auth Surface"],
)


@router.get(
    "/",
    response_model=AdminAuthSurfaceConfigDto,
    summary="Get current admin authentication surface configuration",
)
def get_auth_surface(
    service: AdminAuthSurfaceService = Depends(get_admin_auth_surface_service),
) -> AdminAuthSurfaceConfigDto:
    """Return currently active authentication surface configuration with secrets masked."""
    return service.get_auth_surface(masked=True)


@router.put(
    "/",
    response_model=UpdateAuthSurfaceResponse,
    summary="Update authentication surface configuration with anti-lockout enforcement",
)
def update_auth_surface(
    request: UpdateAuthSurfaceRequest,
    service: AdminAuthSurfaceService = Depends(get_admin_auth_surface_service),
) -> UpdateAuthSurfaceResponse:
    """Apply updated authentication configuration. Rejects deadlock configurations."""
    try:
        return service.update_auth_surface(request)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post(
    "/validate",
    response_model=AuthSurfaceValidationResultDto,
    summary="Dry-run validation of authentication surface configuration",
)
def validate_auth_surface(
    config: AdminAuthSurfaceConfigDto,
    service: AdminAuthSurfaceService = Depends(get_admin_auth_surface_service),
) -> AuthSurfaceValidationResultDto:
    """Pre-validate candidate configuration without applying changes."""
    return service.validate_auth_surface(config)
