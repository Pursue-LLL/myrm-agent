"""API router for Per-Task Workspace Scoping and Cross-Contamination Guard.

[INPUT]
- BindWorkspaceRequest, UpdateAccessModeRequest, VerifyAccessRequest, task_id

[OUTPUT]
- JSON endpoints for task workspace directory binding, access mode toggling,
  path containment verification, and file access audit dossiers.

[POS]
- Server routing layer under `/api/security/workspace`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.workspace_scoper import (
    BindWorkspaceRequest,
    UpdateAccessModeRequest,
    VerifyAccessRequest,
    VerifyAccessResponse,
    WorkspaceAuditReportDto,
    WorkspaceBindingDto,
)
from app.services.security.workspace_scoper_service import get_workspace_scoper_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["security-workspace-scoper"])


@router.post(
    "/bind",
    response_model=WorkspaceBindingDto,
    status_code=status.HTTP_201_CREATED,
    summary="Bind a task to an isolated workspace directory",
)
def bind_workspace(request: BindWorkspaceRequest) -> WorkspaceBindingDto:
    """Assign an isolated directory root to a task with strict containment enforcement."""
    service = get_workspace_scoper_service()
    try:
        return service.bind_workspace(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{task_id}",
    response_model=WorkspaceBindingDto,
    summary="Get active workspace binding for a task",
)
def get_binding(task_id: str) -> WorkspaceBindingDto:
    """Retrieve workspace binding and containment mode for the specified task."""
    service = get_workspace_scoper_service()
    binding = service.get_binding(task_id)
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No workspace binding found for task '{task_id}'",
        )
    return binding


@router.post(
    "/{task_id}/mode",
    response_model=WorkspaceBindingDto,
    summary="Update access mode for a task workspace",
)
def update_access_mode(task_id: str, request: UpdateAccessModeRequest) -> WorkspaceBindingDto:
    """Toggle between scoped_strict (default) and full_system_access mode."""
    service = get_workspace_scoper_service()
    try:
        return service.update_access_mode(task_id, request.access_mode)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/{task_id}/verify-access",
    response_model=VerifyAccessResponse,
    summary="Verify if a file path is permitted within the task workspace",
)
def verify_access(task_id: str, request: VerifyAccessRequest) -> VerifyAccessResponse:
    """Verify file containment and log access attempt into audit dossier."""
    service = get_workspace_scoper_service()
    try:
        return service.verify_access(task_id, request.target_path, request.action)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{task_id}/audit-report",
    response_model=WorkspaceAuditReportDto,
    summary="Retrieve task workspace containment audit dossier",
)
def get_audit_report(task_id: str) -> WorkspaceAuditReportDto:
    """Retrieve full audit trail of file accesses, modifications, and blocked cross-contamination attempts."""
    service = get_workspace_scoper_service()
    try:
        return service.get_audit_report(task_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
