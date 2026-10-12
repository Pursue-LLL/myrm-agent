"""REST API router for integration retained context governance, purge, and provenance revocation.

[INPUT]
- fastapi::{APIRouter, Depends, HTTPException, Query}
- app.schemas.integration_purge::{
    DisconnectWithPurgeRequest,
    DisconnectWithPurgeResponse,
    ProvenanceRevocationAuditItem,
    RetainedContextSummaryResponse,
  }
- app.services.memory.integration_purge_service::{
    IntegrationContextPurgeService,
    get_integration_purge_service,
  }

[OUTPUT]
- router: APIRouter mounted at /api/integrations/retained-context

[POS]
REST API endpoints allowing the frontend and operators to audit retained connector
data, execute privacy-first disconnects with optional purge, and view audit trails (Topic 01 Item 179).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.integration_purge import (
    DisconnectWithPurgeRequest,
    DisconnectWithPurgeResponse,
    ProvenanceRevocationAuditItem,
    RetainedContextSummaryResponse,
)
from app.services.memory.integration_purge_service import (
    IntegrationContextPurgeService,
    get_integration_purge_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/summary/{integration_id}",
    response_model=RetainedContextSummaryResponse,
    summary="Get retained context summary for an integration",
)
async def get_retained_context_summary(
    integration_id: str,
    provider_type: str = Query(
        default="external_integration",
        description="Category of provider (oauth_provider, mcp_server, external_integration)",
    ),
    service: IntegrationContextPurgeService = Depends(get_integration_purge_service),
) -> RetainedContextSummaryResponse:
    """Inspect and return a transparent accounting snapshot of context retained from a connector."""
    try:
        return await service.inspect_retained_context(integration_id, provider_type=provider_type)
    except Exception as exc:
        logger.error("Failed auditing retained context for '%s': %s", integration_id, exc)
        raise HTTPException(
            status_code=500, detail=f"Failed auditing retained context: {exc}"
        ) from exc


@router.post(
    "/disconnect-with-purge/{integration_id}",
    response_model=DisconnectWithPurgeResponse,
    summary="Disconnect an integration with optional context purge and provenance revocation",
)
async def disconnect_with_purge(
    integration_id: str,
    request: DisconnectWithPurgeRequest,
    provider_type: str = Query(
        default="external_integration",
        description="Category of provider",
    ),
    actor: str = Query(default="user", description="Subject triggering the purge"),
    service: IntegrationContextPurgeService = Depends(get_integration_purge_service),
) -> DisconnectWithPurgeResponse:
    """Execute connector disconnect with selectable retention: preserve context or purge & revoke."""
    try:
        return await service.disconnect_and_purge(
            integration_id,
            request,
            provider_type=provider_type,
            actor=actor,
        )
    except Exception as exc:
        logger.error("Failed executing disconnect & purge for '%s': %s", integration_id, exc)
        raise HTTPException(
            status_code=500, detail=f"Failed executing disconnect and purge: {exc}"
        ) from exc


@router.get(
    "/revocations",
    response_model=list[ProvenanceRevocationAuditItem],
    summary="List all recorded provenance revocation ledger records",
)
async def list_revocation_records(
    service: IntegrationContextPurgeService = Depends(get_integration_purge_service),
) -> list[ProvenanceRevocationAuditItem]:
    """Return historical provenance revocation audit records for compliance and traceability."""
    try:
        return await service.get_revocation_audit_log()
    except Exception as exc:
        logger.error("Failed fetching revocation audit records: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Failed fetching revocation audit records: {exc}"
        ) from exc


@router.post(
    "/reinstate/{integration_id}",
    summary="Reinstate a previously revoked provenance source anchor",
)
async def reinstate_provenance(
    integration_id: str,
    service: IntegrationContextPurgeService = Depends(get_integration_purge_service),
) -> dict[str, str | bool]:
    """Reinstate an integration provenance when reconnected by the user."""
    try:
        reinstated = await service.reinstate_provenance(integration_id)
        return {"integration_id": integration_id, "reinstated": reinstated}
    except Exception as exc:
        logger.error("Failed reinstating provenance for '%s': %s", integration_id, exc)
        raise HTTPException(
            status_code=500, detail=f"Failed reinstating provenance: {exc}"
        ) from exc
