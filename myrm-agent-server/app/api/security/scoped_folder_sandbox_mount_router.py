"""API Router for Scoped Folder Permission Dialog and Sandbox Dynamic Mount Suite.

[POS] app/api/security/scoped_folder_sandbox_mount_router.py
[INPUT] fastapi, app.schemas.scoped_folder_sandbox_mount, app.services.security.scoped_folder_sandbox_mount_service
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.scoped_folder_sandbox_mount import (
    DynamicMountSpecDTO,
    RevokeGrantResponse,
    ScopedFolderGrantDTO,
    ScopedFolderGrantRequest,
    ValidatePathSecurityRequest,
    ValidatePathSecurityResponse,
)
from app.services.security.scoped_folder_sandbox_mount_service import (
    ScopedFolderSandboxMountService,
    get_scoped_folder_mount_service,
)

router = APIRouter(
    prefix="/scoped-folder-mount",
    tags=["Security - Scoped Folder Permission & Sandbox Dynamic Mount"],
)


@router.post(
    "/validate-path",
    response_model=ValidatePathSecurityResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate host directory safety against system and credential blacklists",
)
def validate_path_endpoint(
    request: ValidatePathSecurityRequest,
    service: ScopedFolderSandboxMountService = Depends(
        get_scoped_folder_mount_service
    ),
) -> ValidatePathSecurityResponse:
    """Pre-flight check verifying candidate directory does not touch sensitive operating system or credential vaults."""
    return service.validate_path_security(request)


@router.post(
    "/grants/request",
    response_model=ScopedFolderGrantDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Authorize and dynamically project a scoped folder into the sandbox",
)
def request_folder_grant_endpoint(
    request: ScopedFolderGrantRequest,
    service: ScopedFolderSandboxMountService = Depends(
        get_scoped_folder_mount_service
    ),
) -> ScopedFolderGrantDTO:
    """Authorize a host directory and create virtual mount point under /workspace/granted/<slug>."""
    try:
        return service.grant_folder_access(request)
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err
    except (ValueError, KeyError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.get(
    "/grants/{grant_id}/mount-spec",
    response_model=DynamicMountSpecDTO,
    status_code=status.HTTP_200_OK,
    summary="Fetch container virtualization mount specification for grant",
)
def get_mount_spec_endpoint(
    grant_id: str,
    service: ScopedFolderSandboxMountService = Depends(
        get_scoped_folder_mount_service
    ),
) -> DynamicMountSpecDTO:
    """Retrieve virtual mount spec containing host source, sandbox target, and read-only flags."""
    spec = service.get_mount_spec(grant_id)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active mount specification for grant '{grant_id}' not found.",
        )
    return spec


@router.post(
    "/grants/{grant_id}/revoke",
    response_model=RevokeGrantResponse,
    status_code=status.HTTP_200_OK,
    summary="Immediately revoke folder grant and tear down sandbox mount projection",
)
def revoke_folder_grant_endpoint(
    grant_id: str,
    service: ScopedFolderSandboxMountService = Depends(
        get_scoped_folder_mount_service
    ),
) -> RevokeGrantResponse:
    """Revoke authorization lease and dismount dynamic folder projection."""
    return service.revoke_grant(grant_id)


@router.get(
    "/grants",
    response_model=list[ScopedFolderGrantDTO],
    status_code=status.HTTP_200_OK,
    summary="List active or all historical scoped folder grants",
)
def list_grants_endpoint(
    active_only: bool = Query(default=True, description="Filter for active, unexpired grants only"),
    service: ScopedFolderSandboxMountService = Depends(
        get_scoped_folder_mount_service
    ),
) -> list[ScopedFolderGrantDTO]:
    """Retrieve list of currently mounted or historical folder grants."""
    if active_only:
        return service.list_active_grants()
    return service.list_all_grants()
