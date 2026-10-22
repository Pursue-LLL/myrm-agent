"""REST API router for External CLI Subagent Adapter Bridge and Subscription Passthrough."""

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.agent.sub_agents.cli_passthrough import (
    BundleNotFoundError,
    PrivacyDisclosureRequiredError,
    WorkspaceEscalationForbiddenError,
)
from app.schemas.cli_passthrough import (
    AuditRecordsResponse,
    BundlesListResponse,
    CliDelegationExecuteRequest,
    CliExecutionResultDTO,
    PrivacyDisclosureAcknowledgeRequest,
    PrivacyDisclosureCreateRequest,
    PrivacyDisclosureDTO,
)
from app.services.agent.cli_passthrough_service import (
    CliPassthroughService,
    get_cli_passthrough_service,
)

router = APIRouter(prefix="/agents/cli-passthrough", tags=["External CLI Passthrough"])


@router.get(
    "/bundles",
    response_model=BundlesListResponse,
    summary="List available external CLI subagent profile bundles with BYOS status",
)
async def list_cli_bundles(
    service: CliPassthroughService = Depends(get_cli_passthrough_service),
) -> BundlesListResponse:
    """Retrieve all discoverable CLI bundles and probe local installation and subscription tier."""
    return service.list_bundles()


@router.post(
    "/disclosures",
    response_model=PrivacyDisclosureDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a transparent privacy disclosure describing context transfer to third-party CLI",
)
async def create_privacy_disclosure(
    req: PrivacyDisclosureCreateRequest,
    service: CliPassthroughService = Depends(get_cli_passthrough_service),
) -> PrivacyDisclosureDTO:
    """Generate a disclosure describing data sent to Claude/Codex/Cursor vendor."""
    return service.create_privacy_disclosure(req)


@router.post(
    "/disclosures/acknowledge",
    response_model=PrivacyDisclosureDTO,
    summary="Acknowledge a privacy disclosure prior to headless CLI task delegation",
)
async def acknowledge_privacy_disclosure(
    req: PrivacyDisclosureAcknowledgeRequest,
    service: CliPassthroughService = Depends(get_cli_passthrough_service),
) -> PrivacyDisclosureDTO:
    """Record explicit human acknowledgment of vendor terms before delegation."""
    try:
        return service.acknowledge_privacy_disclosure(
            disclosure_id=req.disclosure_id, user_acknowledged=req.user_acknowledged
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/execute",
    response_model=CliExecutionResultDTO,
    summary="Headless non-interactive execution via external CLI with BYOS quota",
)
async def execute_cli_delegation(
    req: CliDelegationExecuteRequest,
    service: CliPassthroughService = Depends(get_cli_passthrough_service),
) -> CliExecutionResultDTO:
    """Run headless external CLI subagent with strict privacy and workspace enforcement."""
    try:
        return service.execute_delegated_task(req)
    except PrivacyDisclosureRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Privacy gate violation: {exc}",
        ) from exc
    except WorkspaceEscalationForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Workspace confinement violation: {exc}",
        ) from exc
    except (BundleNotFoundError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/audit-log",
    response_model=AuditRecordsResponse,
    summary="Query tamper-proof egress accounting records for external CLI delegations",
)
async def list_audit_records(
    service: CliPassthroughService = Depends(get_cli_passthrough_service),
) -> AuditRecordsResponse:
    """Retrieve all recorded egress accounting records with SHA-256 hashes."""
    return service.list_audit_records()


@router.delete(
    "/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset CLI passthrough service state (test/maintenance)",
)
async def reset_cli_passthrough(
    service: CliPassthroughService = Depends(get_cli_passthrough_service),
) -> None:
    """Clear in-memory disclosures and audit logs."""
    service.reset()
