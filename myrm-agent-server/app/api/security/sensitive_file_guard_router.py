"""FastAPI router for Sensitive Vault and Credential File Overwrite Deny Guard.

[INPUT]
- HTTP requests via FastAPI for inspecting file access operations and unlock grants.

[OUTPUT]
- APIRouter exposing endpoints for sensitive credential and vault file protection.

[POS]
API presentation layer for credential and vault file overwrite deny guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.sensitive_file_guard import (
    FileUnlockGrantResponse,
    InspectFileOperationRequest,
    InspectFileOperationResponse,
    IssueUnlockGrantRequest,
    RevokeUnlockGrantRequest,
    SensitiveFileAlertResponse,
)
from app.services.security.sensitive_file_guard_service import (
    SensitiveFileGuardService,
    get_sensitive_file_guard_service,
)

router = APIRouter(prefix="/sensitive-file-guard", tags=["sensitive-file-guard"])


@router.post(
    "/inspect",
    response_model=InspectFileOperationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate file write/mutation against sensitive file protection rules",
)
def inspect_file_operation(
    request: InspectFileOperationRequest,
    service: SensitiveFileGuardService = Depends(get_sensitive_file_guard_service),
) -> InspectFileOperationResponse:
    """Evaluate whether a file write, overwrite, append, or delete targets a sensitive vault/credential file."""
    try:
        return service.inspect_file_operation(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid operation type: {exc}",
        ) from exc


@router.post(
    "/unlock",
    response_model=FileUnlockGrantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a temporary unlock authorization token for a sensitive file",
)
def issue_unlock_grant(
    request: IssueUnlockGrantRequest,
    service: SensitiveFileGuardService = Depends(get_sensitive_file_guard_service),
) -> FileUnlockGrantResponse:
    """Issue a time-bounded user authorization token allowing single-file modification."""
    return service.issue_unlock_grant(request)


@router.post(
    "/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke an active unlock authorization token",
)
def revoke_unlock_grant(
    request: RevokeUnlockGrantRequest,
    service: SensitiveFileGuardService = Depends(get_sensitive_file_guard_service),
) -> dict[str, bool]:
    """Immediately invalidate an active unlock token."""
    success = service.revoke_unlock_grant(request.unlock_token)
    return {"success": success}


@router.get(
    "/grants",
    response_model=list[FileUnlockGrantResponse],
    status_code=status.HTTP_200_OK,
    summary="List active unexpired unlock grants",
)
def list_active_grants(
    service: SensitiveFileGuardService = Depends(get_sensitive_file_guard_service),
) -> list[FileUnlockGrantResponse]:
    """Retrieve all current unexpired unlock authorizations."""
    return service.list_active_grants()


@router.get(
    "/alerts",
    response_model=list[SensitiveFileAlertResponse],
    status_code=status.HTTP_200_OK,
    summary="List audit alerts for blocked sensitive file overwrite attempts",
)
def get_alerts(
    session_id: str | None = Query(default=None),
    service: SensitiveFileGuardService = Depends(get_sensitive_file_guard_service),
) -> list[SensitiveFileAlertResponse]:
    """Retrieve security violation audit logs."""
    return service.get_alerts(session_id)
