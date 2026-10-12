"""API router for Session Entity Provenance Gate, Staging Approvals, and Hard Caps.

[INPUT]
- RegisterSeenEntitiesRequest, CheckProvenanceRequest, StageChangeRequest
- IssueHostTokenRequest, ApplyStagedChangeRequest, CheckCapsRequest

[OUTPUT]
- RegisterSeenEntitiesResponse, CheckProvenanceResponse, StagedChangeDraftDto
- HostApprovalTokenDto, CheckCapsResponse

[POS]
Server API layer. Exposes REST endpoints for Anthropic Commerce Agents-style security gates.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.core.security.provenance_gate import StagedChangeNotApprovedError

from app.schemas.provenance_staging import (
    ApplyStagedChangeRequest,
    CheckCapsRequest,
    CheckCapsResponse,
    CheckProvenanceRequest,
    CheckProvenanceResponse,
    HostApprovalTokenDto,
    IssueHostTokenRequest,
    RegisterSeenEntitiesRequest,
    RegisterSeenEntitiesResponse,
    RejectStagedChangeRequest,
    StageChangeRequest,
    StagedChangeDraftDto,
)
from app.services.security.provenance_staging_service import (
    default_provenance_staging_service,
)

router = APIRouter(prefix="/provenance-staging", tags=["provenance-staging"])


@router.post("/register-seen", response_model=RegisterSeenEntitiesResponse)
async def register_seen_entities(
    request: RegisterSeenEntitiesRequest,
) -> RegisterSeenEntitiesResponse:
    """Register observed entity IDs returned by authenticated read query tools."""
    return default_provenance_staging_service.register_seen_entities(request)


@router.post("/check-provenance", response_model=CheckProvenanceResponse)
async def check_provenance(
    request: CheckProvenanceRequest,
) -> CheckProvenanceResponse:
    """Verify whether target entity was observed before permitting mutation."""
    return default_provenance_staging_service.check_provenance(request)


@router.post("/stage", response_model=StagedChangeDraftDto)
async def stage_change(
    request: StageChangeRequest,
) -> StagedChangeDraftDto:
    """Stage a proposed high-impact mutation draft prior to host authorization."""
    return default_provenance_staging_service.stage_change(request)


@router.post("/issue-token", response_model=HostApprovalTokenDto)
async def issue_host_token(
    request: IssueHostTokenRequest,
) -> HostApprovalTokenDto:
    """Issue an authentic host signed authorization token for a staged change."""
    try:
        return default_provenance_staging_service.issue_host_token(request)
    except StagedChangeNotApprovedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/apply", response_model=StagedChangeDraftDto)
async def apply_staged_change(
    request: ApplyStagedChangeRequest,
) -> StagedChangeDraftDto:
    """Apply a staged change presenting an authentic host signed token."""
    try:
        return default_provenance_staging_service.apply_staged_change(request)
    except StagedChangeNotApprovedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/reject", response_model=StagedChangeDraftDto)
async def reject_staged_change(
    request: RejectStagedChangeRequest,
) -> StagedChangeDraftDto:
    """Reject and cancel a staged mutation draft."""
    try:
        return default_provenance_staging_service.reject_staged_change(request)
    except StagedChangeNotApprovedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/staged/{staged_id}", response_model=StagedChangeDraftDto)
async def get_staged_change(staged_id: str) -> StagedChangeDraftDto:
    """Get staged change draft details by ID."""
    draft = default_provenance_staging_service.get_staged_change(staged_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Staged change draft not found")
    return draft


@router.get("/staged", response_model=list[StagedChangeDraftDto])
async def list_staged_changes(
    session_id: str | None = Query(default=None, description="Optional session filter"),
) -> list[StagedChangeDraftDto]:
    """List active staged mutation drafts."""
    return default_provenance_staging_service.list_staged_changes(session_id=session_id)


@router.post("/check-caps", response_model=CheckCapsResponse)
async def check_business_caps(
    request: CheckCapsRequest,
) -> CheckCapsResponse:
    """Validate numerical parameters against hardcoded Python caps and return alternatives."""
    return default_provenance_staging_service.check_caps(request)
