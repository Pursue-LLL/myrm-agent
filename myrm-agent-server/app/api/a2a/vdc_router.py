"""REST API for Verifiable AI Delegation Credentials (VDC) and Dual-Signed Negotiation Ledger.

[POS]
Provides endpoints for:
1. Enterprise VDC credential issuance and offline attestation.
2. Cross-enterprise dual-signed A2A negotiation steps and contract seals.
3. Cryptographic negotiation chain verification and legal-grade audit dossier export.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.schemas.a2a_vdc import (
    DualSignedNegotiationBlock,
    NegotiationLedgerAuditReport,
    NegotiationTerms,
    VdcVerificationResult,
    VerifiableDelegationCredential,
)
from app.services.a2a.negotiation_ledger import get_negotiation_ledger
from app.services.a2a.vdc_service import get_vdc_service

router = APIRouter(prefix="/vdc", tags=["a2a-vdc"])


class IssueVdcRequest(BaseModel):
    """Payload to issue a Verifiable Delegation Credential to an agent."""

    issuer_did: str = Field(..., description="Corporate DID of the issuing entity")
    issuer_name: str = Field(..., description="Legal company name")
    holder_agent_id: str = Field(..., description="Agent persona ID authorized")
    holder_name: str = Field(..., description="Agent display name / business role")
    max_transaction_amount: float = Field(..., gt=0, description="Authorized spending ceiling")
    allowed_actions: list[str] = Field(..., min_length=1, description="Whitelisted commercial actions")
    validity_duration_seconds: float = Field(default=86400 * 30, description="Validity period in seconds")
    currency: str = Field(default="USD", description="Currency standard code")
    issuer_public_key: str = Field(
        default="pk_ed25519_acme_master_key_fingerprint",
        description="Public key fingerprint of issuing corporation",
    )


class VerifyVdcRequest(BaseModel):
    """Payload to verify an incoming peer agent's delegation credential."""

    vdc: VerifiableDelegationCredential = Field(..., description="Full credential object")
    proposed_action: str | None = Field(None, description="Action proposed by the agent")
    proposed_amount: float | None = Field(None, description="Proposed transaction amount")


class AppendNegotiationStepRequest(BaseModel):
    """Payload to record a dual-signed negotiation step into the ledger."""

    session_id: str = Field(..., description="Negotiation session identifier")
    initiator_agent_id: str = Field(..., description="Agent making the proposal/counter-offer")
    responder_agent_id: str = Field(..., description="Peer agent responding/counter-signing")
    initiator_vdc: VerifiableDelegationCredential = Field(..., description="VDC of initiating agent")
    responder_vdc: VerifiableDelegationCredential = Field(..., description="VDC of responding agent")
    terms: NegotiationTerms = Field(..., description="Agreed or proposed commercial terms")
    initiator_signature: str = Field(..., description="Initiator signature over terms digest")
    responder_signature: str = Field(..., description="Responder signature over terms digest")


@router.post("/issue", response_model=VerifiableDelegationCredential)
async def issue_vdc_credential(payload: IssueVdcRequest) -> VerifiableDelegationCredential:
    """Issue a cryptographically signed VDC authorizing an agent to perform commercial transactions."""
    service = get_vdc_service()
    return service.issue_vdc(
        issuer_did=payload.issuer_did,
        issuer_name=payload.issuer_name,
        holder_agent_id=payload.holder_agent_id,
        holder_name=payload.holder_name,
        max_transaction_amount=payload.max_transaction_amount,
        allowed_actions=payload.allowed_actions,
        validity_duration_seconds=payload.validity_duration_seconds,
        currency=payload.currency,
        issuer_public_key=payload.issuer_public_key,
    )


@router.post("/verify", response_model=VdcVerificationResult)
async def verify_vdc_credential(payload: VerifyVdcRequest) -> VdcVerificationResult:
    """Verify an agent's VDC credential authenticity, time bounds, and transaction limits."""
    service = get_vdc_service()
    return service.verify_vdc(
        vdc=payload.vdc,
        proposed_action=payload.proposed_action,
        proposed_amount=payload.proposed_amount,
    )


@router.post("/negotiation/step", response_model=DualSignedNegotiationBlock)
async def append_negotiation_step(payload: AppendNegotiationStepRequest) -> DualSignedNegotiationBlock:
    """Append a dual-signed commercial negotiation block into the immutable ledger."""
    ledger = get_negotiation_ledger()
    try:
        return await ledger.append_step(
            session_id=payload.session_id,
            initiator_agent_id=payload.initiator_agent_id,
            responder_agent_id=payload.responder_agent_id,
            initiator_vdc=payload.initiator_vdc,
            responder_vdc=payload.responder_vdc,
            terms=payload.terms,
            initiator_signature=payload.initiator_signature,
            responder_signature=payload.responder_signature,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/negotiation/{session_id}/ledger", response_model=list[DualSignedNegotiationBlock])
async def get_negotiation_ledger_blocks(
    session_id: str = Path(..., description="Negotiation session ID"),
) -> list[DualSignedNegotiationBlock]:
    """Retrieve all negotiation blocks recorded in an A2A session."""
    ledger = get_negotiation_ledger()
    return ledger.get_session_blocks(session_id)


class ChainVerificationResultSchema(BaseModel):
    """Result of negotiation chain integrity check."""

    session_id: str = Field(..., description="Session identifier")
    chain_intact: bool = Field(..., description="True if hash chain and all dual signatures are intact")
    error: str | None = Field(None, description="Discrepancy reason if tampered")
    total_blocks: int = Field(..., description="Number of blocks verified")


@router.get("/negotiation/{session_id}/verify", response_model=ChainVerificationResultSchema)
async def verify_negotiation_ledger_chain(
    session_id: str = Path(..., description="Negotiation session ID"),
    initiator_public_key: str = Query(..., description="Public key of initiating party"),
    responder_public_key: str = Query(..., description="Public key of responding party"),
) -> ChainVerificationResultSchema:
    """Verify hash continuity and dual signatures across an entire A2A commercial session."""
    ledger = get_negotiation_ledger()
    intact, err = ledger.verify_session_chain(
        session_id=session_id,
        initiator_public_key=initiator_public_key,
        responder_public_key=responder_public_key,
    )
    blocks = ledger.get_session_blocks(session_id)
    return ChainVerificationResultSchema(
        session_id=session_id,
        chain_intact=intact,
        error=err,
        total_blocks=len(blocks),
    )


@router.get("/negotiation/{session_id}/export-dossier", response_model=NegotiationLedgerAuditReport)
async def export_negotiation_audit_dossier(
    session_id: str = Path(..., description="Negotiation session ID"),
    initiator_did: str = Query(..., description="Corporate DID of initiating party"),
    responder_did: str = Query(..., description="Corporate DID of responding party"),
    initiator_public_key: str = Query(..., description="Public key of initiating party"),
    responder_public_key: str = Query(..., description="Public key of responding party"),
) -> NegotiationLedgerAuditReport:
    """Export complete legal-grade non-repudiation audit dossier for the commercial negotiation."""
    ledger = get_negotiation_ledger()
    return ledger.export_audit_dossier(
        session_id=session_id,
        initiator_did=initiator_did,
        responder_did=responder_did,
        initiator_public_key=initiator_public_key,
        responder_public_key=responder_public_key,
    )
