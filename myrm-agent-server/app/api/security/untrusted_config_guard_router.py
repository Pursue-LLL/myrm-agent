"""FastAPI router for Untrusted Project Config Isolation and Preflight Diagnostic Gate.

[INPUT]
- HTTP requests via FastAPI for untrusted workspace config validation and diagnostics.

[OUTPUT]
- APIRouter exposing endpoints for preflight untrusted configuration isolation.

[POS]
API presentation layer for untrusted project config isolation and safety checks.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.schemas.untrusted_config_guard import (
    DiagnosticResultResponse,
    PreflightValidateRequest,
    ResolveConfigRequest,
    TrustWorkspaceRequest,
    TrustWorkspaceResponse,
)
from app.services.security.untrusted_config_guard_service import (
    UntrustedConfigGuardService,
    get_untrusted_config_guard_service,
)

router = APIRouter(prefix="/config-guard", tags=["config-guard"])


@router.post(
    "/resolve",
    response_model=DiagnosticResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve effective configuration respecting workspace trust boundaries",
)
def resolve_config(
    request: ResolveConfigRequest,
    service: UntrustedConfigGuardService = Depends(
        get_untrusted_config_guard_service
    ),
) -> DiagnosticResultResponse:
    """Resolve config across 3 tiers (local trusted, global, defaults) with untrusted isolation."""
    return service.resolve_config(request)


@router.post(
    "/preflight-validate",
    response_model=DiagnosticResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute static preflight schema diagnostics on raw configuration",
)
def preflight_validate(
    request: PreflightValidateRequest,
    service: UntrustedConfigGuardService = Depends(
        get_untrusted_config_guard_service
    ),
) -> DiagnosticResultResponse:
    """Perform preflight checks: forbid unknown keys, assert versions, and check security flags."""
    return service.validate_preflight(request)


@router.post(
    "/trust",
    response_model=TrustWorkspaceResponse,
    status_code=status.HTTP_200_OK,
    summary="Set workspace trust status",
)
def set_workspace_trust(
    request: TrustWorkspaceRequest,
    service: UntrustedConfigGuardService = Depends(
        get_untrusted_config_guard_service
    ),
) -> TrustWorkspaceResponse:
    """Explicitly mark a workspace as trusted or untrusted."""
    is_trusted = service.set_workspace_trust(
        request.workspace_path, request.trusted
    )
    return TrustWorkspaceResponse(
        workspace_path=request.workspace_path,
        is_trusted=is_trusted,
    )


@router.get(
    "/trust-status",
    response_model=TrustWorkspaceResponse,
    status_code=status.HTTP_200_OK,
    summary="Check whether a workspace is currently trusted",
)
def get_workspace_trust_status(
    workspace_path: str = Query(..., description="Target workspace directory"),
    service: UntrustedConfigGuardService = Depends(
        get_untrusted_config_guard_service
    ),
) -> TrustWorkspaceResponse:
    """Query trust status of a specific workspace."""
    is_trusted = service.is_workspace_trusted(workspace_path)
    return TrustWorkspaceResponse(
        workspace_path=workspace_path,
        is_trusted=is_trusted,
    )
