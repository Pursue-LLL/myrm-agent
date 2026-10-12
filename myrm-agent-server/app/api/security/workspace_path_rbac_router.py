"""FastAPI router for Granular Workspace Path RBAC & Denial Audit.

[INPUT]
- JSON payloads configuring workspace path policies, testing file operations, and querying audit ledgers.

[OUTPUT]
- Serialized verdicts, UI denial cards, and structured filesystem audit records.

[POS]
- REST API layer providing enterprise filesystem access control and triple write defense.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.workspace_path_rbac import (
    AuditLedgerEntryDto,
    AuditStatsDto,
    CheckPathAccessRequest,
    CheckPathAccessResponse,
    RegisterWorkspacePolicyRequest,
    WorkspacePolicyDto,
)
from app.services.security.workspace_path_rbac_service import (
    WorkspacePathRbacService,
    get_workspace_path_rbac_service,
)

router = APIRouter(
    prefix="/workspace-path-rbac",
    tags=["Security: Workspace Path RBAC"],
)


@router.post(
    "/policies",
    response_model=WorkspacePolicyDto,
    status_code=status.HTTP_201_CREATED,
    summary="Register declarative workspace path RBAC policy",
)
def register_policy(
    request: RegisterWorkspacePolicyRequest,
    service: WorkspacePathRbacService = Depends(get_workspace_path_rbac_service),
) -> WorkspacePolicyDto:
    """Register or update a path RBAC policy with explicit RO/RW rules."""
    return service.register_policy(request.policy)


@router.get(
    "/policies/{policy_id}",
    response_model=WorkspacePolicyDto,
    summary="Get registered workspace path policy",
)
def get_policy(
    policy_id: str,
    service: WorkspacePathRbacService = Depends(get_workspace_path_rbac_service),
) -> WorkspacePolicyDto:
    """Retrieve workspace path RBAC policy by identifier."""
    policy = service.get_policy(policy_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{policy_id}' not found.",
        )
    return policy


@router.post(
    "/check",
    response_model=CheckPathAccessResponse,
    summary="Test file operation permission against policy and log to audit ledger",
)
def check_access(
    request: CheckPathAccessRequest,
    service: WorkspacePathRbacService = Depends(get_workspace_path_rbac_service),
) -> CheckPathAccessResponse:
    """Test filesystem action permissions. Rejects unpermitted writes with auto-reroute cards."""
    return service.check_access(request)


@router.get(
    "/audit-ledger",
    response_model=list[AuditLedgerEntryDto],
    summary="Query structured filesystem audit ledger",
)
def query_audit_ledger(
    session_id: str | None = Query(default=None, description="Filter by session ID"),
    agent_id: str | None = Query(default=None, description="Filter by agent ID"),
    user_identity: str | None = Query(default=None, description="Filter by user identity"),
    granted: bool | None = Query(default=None, description="Filter by granted status"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max entries to return"),
    service: WorkspacePathRbacService = Depends(get_workspace_path_rbac_service),
) -> list[AuditLedgerEntryDto]:
    """Retrieve audit ledger records tracking file operations and denials."""
    return service.query_audit_ledger(
        session_id=session_id,
        agent_id=agent_id,
        user_identity=user_identity,
        granted=granted,
        limit=limit,
    )


@router.get(
    "/audit-stats",
    response_model=AuditStatsDto,
    summary="Get aggregated filesystem audit statistics",
)
def get_audit_stats(
    service: WorkspacePathRbacService = Depends(get_workspace_path_rbac_service),
) -> AuditStatsDto:
    """Return aggregated file access statistics and denial breakdowns."""
    return service.get_audit_stats()
