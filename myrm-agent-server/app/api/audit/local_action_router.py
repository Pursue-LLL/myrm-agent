"""REST API for Local Agent Action Ledger, Egress Footprints, and Privacy Inspector.

[POS]
Provides endpoints for:
1. Querying and verifying cryptographically chained local data access records.
2. Querying and exporting outbound network egress footprints.
3. Fetching aggregated Privacy Inspector metrics for WebUI transparency.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.schemas.local_action_audit import (
    EgressFootprintReceipt,
    LocalActionAuditEntry,
    PrivacyInspectorSummary,
)
from app.services.approvals.financial_gate import get_financial_sign_off_gate
from app.services.audit.egress_footprint_ledger import get_egress_footprint_ledger
from app.services.audit.local_action_ledger import get_local_action_ledger

router = APIRouter(prefix="/audit/local-actions", tags=["audit-local-actions"])


class ChainVerificationResponse(BaseModel):
    """Integrity verification result of the local action audit ledger."""

    healthy: bool = Field(..., description="True if the entire hash chain and signatures are intact")
    error: str | None = Field(None, description="Details of the first broken link or invalid signature, if any")
    total_entries_verified: int = Field(..., description="Total entries scanned in the verification pass")


class ExportDossierResponse(BaseModel):
    """Combined audit export containing local access entries and outbound network footprints."""

    agent_id: str | None = Field(None, description="Target agent filter or null for all")
    chain_verification: ChainVerificationResponse = Field(..., description="Cryptographic chain health proof")
    local_action_entries: list[LocalActionAuditEntry] = Field(..., description="Chained local data access records")
    egress_footprints: list[EgressFootprintReceipt] = Field(..., description="Outbound network transmission facts")


class RecordLocalAccessRequest(BaseModel):
    """Request payload to manually or middleware-record a local entity access."""

    agent_id: str = Field(..., description="Agent persona identifier")
    target_entity_type: str = Field(..., description="Entity category: email, invoice, id_card, etc.")
    target_entity_id: str = Field(..., description="Unique entity ID or resource path")
    entity_hash: str = Field(..., description="SHA-256 digest of entity data")
    action: str = Field(..., description="Action: read, classify, extract, archive")
    intent_summary: str = Field(..., description="Clear explanation of the agent's intent")
    operator_or_model: str = Field(default="gpt-4o", description="Model or operator invoking the tool")
    session_id: str | None = Field(None, description="Chat session ID")
    task_id: str | None = Field(None, description="Background task ID")


@router.post("", response_model=LocalActionAuditEntry)
async def record_local_action(payload: RecordLocalAccessRequest) -> LocalActionAuditEntry:
    """Record an agent's access to a local sensitive entity into the append-only ledger."""
    ledger = get_local_action_ledger()
    return await ledger.record_access(
        agent_id=payload.agent_id,
        target_entity_type=payload.target_entity_type,
        target_entity_id=payload.target_entity_id,
        entity_hash=payload.entity_hash,
        action=payload.action,
        intent_summary=payload.intent_summary,
        operator_or_model=payload.operator_or_model,
        session_id=payload.session_id,
        task_id=payload.task_id,
    )


@router.get("", response_model=list[LocalActionAuditEntry])
async def list_local_actions(
    agent_id: str | None = Query(None, description="Filter by agent identifier"),
    entity_type: str | None = Query(None, description="Filter by entity type (email, invoice, etc.)"),
    limit: int = Query(50, ge=1, le=500, description="Max entries to return"),
) -> list[LocalActionAuditEntry]:
    """List recent local data access records in reverse chronological order."""
    ledger = get_local_action_ledger()
    return ledger.query_entries(agent_id=agent_id, entity_type=entity_type, limit=limit)


@router.get("/verify", response_model=ChainVerificationResponse)
async def verify_ledger_chain() -> ChainVerificationResponse:
    """Verify cryptographic integrity of the local action ledger hash chain and HMAC signatures."""
    ledger = get_local_action_ledger()
    healthy, err = ledger.verify_chain()
    total = len(ledger.query_entries(limit=10000))
    return ChainVerificationResponse(
        healthy=healthy,
        error=err,
        total_entries_verified=total,
    )


@router.get("/egress-footprints", response_model=list[EgressFootprintReceipt])
async def list_egress_footprints(
    agent_id: str | None = Query(None, description="Filter by agent identifier"),
    session_id: str | None = Query(None, description="Filter by session identifier"),
    target_host: str | None = Query(None, description="Filter by external destination host"),
    limit: int = Query(50, ge=1, le=500, description="Max receipts to return"),
) -> list[EgressFootprintReceipt]:
    """List outbound network transmission facts. These cannot be revoked, only audited."""
    egress_ledger = get_egress_footprint_ledger()
    return egress_ledger.query_footprints(
        agent_id=agent_id,
        session_id=session_id,
        target_host=target_host,
        limit=limit,
    )


@router.get("/inspector-summary", response_model=PrivacyInspectorSummary)
async def get_privacy_inspector_summary(
    agent_id: str | None = Query(None, description="Filter by agent identifier"),
) -> PrivacyInspectorSummary:
    """Compute aggregated privacy metrics for WebUI inspector (today's reads, drafts, interceptions)."""
    ledger = get_local_action_ledger()
    summary = ledger.compute_inspector_summary(agent_id=agent_id)

    # Augment with financial gate statistics
    gate = get_financial_sign_off_gate()
    drafts = gate.list_drafts(agent_id=agent_id)
    summary.total_financial_interceptions = len(drafts)
    summary.total_pending_signoffs = sum(1 for d in drafts if d.status == "PENDING_SIGNOFF")

    # Augment with egress facts
    egress_ledger = get_egress_footprint_ledger()
    footprints = egress_ledger.query_footprints(agent_id=agent_id, limit=1000)
    summary.total_egress_events = len(footprints)
    summary.top_egress_hosts = egress_ledger.get_top_hosts(agent_id=agent_id, limit=5)

    return summary


@router.get("/export", response_model=ExportDossierResponse)
async def export_audit_dossier(
    agent_id: str | None = Query(None, description="Filter by agent identifier"),
) -> ExportDossierResponse:
    """Export complete audit dossier combining chained access records and egress footprints."""
    ledger = get_local_action_ledger()
    egress_ledger = get_egress_footprint_ledger()

    healthy, err = ledger.verify_chain()
    entries = ledger.query_entries(agent_id=agent_id, limit=5000)
    footprints = egress_ledger.query_footprints(agent_id=agent_id, limit=5000)

    verification = ChainVerificationResponse(
        healthy=healthy,
        error=err,
        total_entries_verified=len(entries),
    )
    return ExportDossierResponse(
        agent_id=agent_id,
        chain_verification=verification,
        local_action_entries=entries,
        egress_footprints=footprints,
    )
