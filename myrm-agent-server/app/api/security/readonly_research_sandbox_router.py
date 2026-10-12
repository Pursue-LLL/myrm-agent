"""
[POS] app/api/security/readonly_research_sandbox_router.py
[INPUT] app.schemas.readonly_research_sandbox, app.services.security.readonly_research_sandbox_service
[OUTPUT] router

FastAPI router for Read-Only Autonomous Research Lease & Immutable Snapshot Sandbox Suite.
Exposes REST endpoints to manage read-only leases, evaluate tool physical stripping,
capture immutable baseline snapshots, stage in-memory CoW files, verify purity, and query shield badges.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.schemas.readonly_research_sandbox import (
    EphemeralFileResponse,
    GrantLeaseRequest,
    PurgeOverlayResponse,
    ReadOnlyLeaseResponse,
    ReadOnlyResearchMetricsResponse,
    RevokeLeaseResponse,
    ShieldBadgeResponse,
    TakeSnapshotRequest,
    ToolEvaluationRequest,
    ToolEvaluationResponse,
    VerifyPurityRequest,
    VerifyPurityResponse,
    WorkspaceSnapshotResponse,
    WriteEphemeralFileRequest,
)
from app.services.security.readonly_research_sandbox_service import (
    ReadOnlyResearchSandboxService,
    get_readonly_research_sandbox_service,
)

router = APIRouter(
    prefix="/readonly-research",
    tags=["Read-Only Research Lease & Immutable Snapshot Sandbox"],
)


@router.post(
    "/lease",
    response_model=ReadOnlyLeaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant dynamic read-only research lease to session",
)
def grant_lease(
    request: GrantLeaseRequest,
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> ReadOnlyLeaseResponse:
    """Grant read-only research lease and enforce physical stripping of side-effect tools."""
    return service.grant_lease(request)


@router.get(
    "/lease/{session_id}",
    response_model=ReadOnlyLeaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect active or expired read-only lease for session",
)
def get_lease(
    session_id: str = Path(..., min_length=1, description="Session identifier"),
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> ReadOnlyLeaseResponse:
    """Retrieve lease descriptor with lazy expiry evaluation."""
    lease = service.get_lease(session_id)
    if lease is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No read-only lease found for session '{session_id}'.",
        )
    return lease


@router.post(
    "/lease/{session_id}/revoke",
    response_model=RevokeLeaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke active read-only lease immediately",
)
def revoke_lease(
    session_id: str = Path(..., min_length=1, description="Session identifier"),
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> RevokeLeaseResponse:
    """Revoke active lease and restore standard tool access."""
    return service.revoke_lease(session_id)


@router.post(
    "/evaluate-tool",
    response_model=ToolEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate if tool is permissible or physically stripped by lease",
)
def evaluate_tool(
    request: ToolEvaluationRequest,
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> ToolEvaluationResponse:
    """Check tool access against active read-only lease whitelist."""
    return service.evaluate_tool(request)


@router.post(
    "/snapshot",
    response_model=WorkspaceSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capture immutable cryptographic baseline snapshot of protected workspace",
)
def take_snapshot(
    request: TakeSnapshotRequest,
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> WorkspaceSnapshotResponse:
    """Lock current workspace file state with SHA-256 root digest."""
    return service.take_snapshot(request)


@router.post(
    "/ephemeral-file",
    response_model=EphemeralFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Write transient research output strictly into memory CoW layer",
)
def write_ephemeral_file(
    request: WriteEphemeralFileRequest,
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> EphemeralFileResponse:
    """Stage calculation chart or temporary intermediate data without disk mutation."""
    return service.write_ephemeral_file(request)


@router.get(
    "/ephemeral-files/{session_id}",
    response_model=list[EphemeralFileResponse],
    status_code=status.HTTP_200_OK,
    summary="List transient files currently staged in in-memory CoW layer",
)
def list_ephemeral_files(
    session_id: str = Path(..., min_length=1, description="Session identifier"),
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> list[EphemeralFileResponse]:
    """Retrieve all files staged in session's memory overlay."""
    return service.list_ephemeral_files(session_id)


@router.post(
    "/purge-overlay/{session_id}",
    response_model=PurgeOverlayResponse,
    status_code=status.HTTP_200_OK,
    summary="Purge and destroy in-memory CoW layer on task completion",
)
def purge_overlay(
    session_id: str = Path(..., min_length=1, description="Session identifier"),
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> PurgeOverlayResponse:
    """Physically destroy all transient files ensuring zero workspace pollution."""
    return service.purge_overlay(session_id)


@router.post(
    "/verify-purity",
    response_model=VerifyPurityResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify workspace files against baseline snapshot for 100% purity",
)
def verify_purity(
    request: VerifyPurityRequest,
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> VerifyPurityResponse:
    """Compare current files against immutable snapshot to confirm zero pollution."""
    return service.verify_purity(request)


@router.get(
    "/badge/{session_id}",
    response_model=ShieldBadgeResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve real-time UI security indicator badge",
)
def get_shield_badge(
    session_id: str = Path(..., min_length=1, description="Session identifier"),
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> ShieldBadgeResponse:
    """Construct real-time security badge for WebUI/desktop header."""
    return service.get_shield_badge(session_id)


@router.get(
    "/metrics",
    response_model=ReadOnlyResearchMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect cumulative telemetry metrics for read-only research sandbox",
)
def get_metrics(
    service: ReadOnlyResearchSandboxService = Depends(
        get_readonly_research_sandbox_service
    ),
) -> ReadOnlyResearchMetricsResponse:
    """Retrieve cumulative statistics across leases, blocked writes, overlays, and purges."""
    return service.get_metrics()
