"""Schemas for Verifiable AI Delegation Credentials (VDC) and Dual-Signed Negotiation Chain.

[POS]
Defines cryptographic structures for:
1. Verifiable Delegation Credentials (VDC): binds an enterprise legal entity to an agent
   with strictly limited financial authorization amounts, actions, and time windows.
2. Dual-Signed Negotiation Blocks: tamper-evident hash chain capturing A2A commercial
   offers, counter-offers, acceptances, and contracts with signatures from both peers.
3. Legal liability and non-repudiation audit dossier models.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Literal

from pydantic import BaseModel, Field


class VerifiableDelegationCredential(BaseModel):
    """Cryptographically signed delegation credential issued by an enterprise to an agent."""

    credential_id: str = Field(..., description="Unique UUID for this delegation credential")
    issuer_did: str = Field(..., description="Decentralized Identifier or corporate ID of issuing entity")
    issuer_name: str = Field(..., description="Legal entity name of issuing corporation")
    holder_agent_id: str = Field(..., description="Agent persona ID authorized by this credential")
    holder_name: str = Field(..., description="Agent display name / business role")
    max_transaction_amount: float = Field(..., gt=0, description="Maximum single-transaction value permitted")
    currency: str = Field(default="USD", description="Currency standard code (e.g. USD, CNY, EUR)")
    valid_from: float = Field(..., description="Unix timestamp starting authorization")
    valid_until: float = Field(..., description="Unix timestamp expiring authorization")
    allowed_actions: list[str] = Field(
        ...,
        min_length=1,
        description="Allowed business actions, e.g. ['procurement', 'quote', 'sign_contract']",
    )
    issuer_public_key: str = Field(..., description="Public key or key fingerprint of issuer")
    signature: str = Field(default="", description="Digital signature certifying credential authenticity")

    def canonical_payload_bytes(self) -> bytes:
        """Deterministic canonical JSON bytes for hashing and signature verification."""
        payload: dict[str, str | float | list[str]] = {
            "credential_id": self.credential_id,
            "issuer_did": self.issuer_did,
            "issuer_name": self.issuer_name,
            "holder_agent_id": self.holder_agent_id,
            "holder_name": self.holder_name,
            "max_transaction_amount": self.max_transaction_amount,
            "currency": self.currency,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "allowed_actions": sorted(self.allowed_actions),
            "issuer_public_key": self.issuer_public_key,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    def compute_digest(self) -> str:
        """Compute SHA-256 digest of canonical credential payload."""
        return hashlib.sha256(self.canonical_payload_bytes()).hexdigest()

    def sign(self, issuer_secret_key: str) -> str:
        """Compute HMAC-SHA256 signature for credential."""
        mac = hmac.new(
            issuer_secret_key.encode("utf-8"),
            self.canonical_payload_bytes(),
            hashlib.sha256,
        )
        return mac.hexdigest()

    def verify(self, issuer_secret_key: str) -> bool:
        """Verify signature matches canonical payload."""
        if not self.signature:
            return False
        expected_sig = self.sign(issuer_secret_key)
        return hmac.compare_digest(self.signature, expected_sig)


class VdcVerificationResult(BaseModel):
    """Result of verifying an incoming peer agent's delegation credential."""

    is_valid: bool = Field(..., description="Overall verification outcome")
    failure_reason: str | None = Field(None, description="Detailed explanation if invalid")
    credential_id: str = Field(..., description="Credential identifier inspected")
    issuer_did: str = Field(..., description="Issuer entity ID")
    holder_agent_id: str = Field(..., description="Authorized agent ID")
    amount_permitted: bool = Field(..., description="True if proposed amount <= max_transaction_amount")
    action_permitted: bool = Field(..., description="True if proposed action is in allowed_actions")
    is_expired: bool = Field(..., description="True if outside valid_from .. valid_until timeframe")


class NegotiationTerms(BaseModel):
    """Commercial terms of an offer or counter-offer during A2A negotiation."""

    terms_id: str = Field(..., description="Unique terms identifier")
    action: Literal["quote", "counter_offer", "acceptance", "final_contract"] = Field(
        ...,
        description="Negotiation intent phase",
    )
    item_description: str = Field(..., description="Product, service, or resource scope")
    quantity: int = Field(..., ge=1, description="Quantity of units")
    unit_price: float = Field(..., ge=0, description="Price per unit")
    total_amount: float = Field(..., ge=0, description="Total transaction amount")
    currency: str = Field(default="USD", description="Currency code")
    delivery_deadline: str = Field(..., description="Agreed fulfillment timeline or SLA")
    terms_digest: str = Field(..., description="Cryptographic SHA-256 digest of terms payload")

    @classmethod
    def compute_digest(
        cls,
        action: str,
        item_description: str,
        quantity: int,
        unit_price: float,
        total_amount: float,
        currency: str,
        delivery_deadline: str,
    ) -> str:
        """Compute SHA-256 digest for negotiation terms."""
        raw = f"{action}|{item_description}|{quantity}|{unit_price}|{total_amount}|{currency}|{delivery_deadline}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DualSignedNegotiationBlock(BaseModel):
    """Immutable block in the dual-signed A2A negotiation ledger."""

    block_id: str = Field(..., description="Unique block identifier")
    session_id: str = Field(..., description="A2A negotiation session ID")
    step_index: int = Field(..., ge=0, description="Sequential step index in negotiation (0-based)")
    initiator_agent_id: str = Field(..., description="Agent proposing this step")
    responder_agent_id: str = Field(..., description="Peer agent evaluating/countering this step")
    initiator_vdc_id: str = Field(..., description="VDC of initiating agent")
    responder_vdc_id: str = Field(..., description="VDC of responding agent")
    terms: NegotiationTerms = Field(..., description="Agreed or proposed commercial terms")
    initiator_signature: str = Field(..., description="Digital signature of initiator on terms digest")
    responder_signature: str = Field(..., description="Digital signature of responder on terms digest")
    prev_block_hash: str = Field(..., description="SHA-256 digest of previous block in session")
    block_hash: str = Field(default="", description="SHA-256 digest of this block payload")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of block creation")

    def canonical_payload_bytes(self) -> bytes:
        """Deterministic canonical bytes for block hashing."""
        payload: dict[str, str | int | float] = {
            "block_id": self.block_id,
            "session_id": self.session_id,
            "step_index": self.step_index,
            "initiator_agent_id": self.initiator_agent_id,
            "responder_agent_id": self.responder_agent_id,
            "initiator_vdc_id": self.initiator_vdc_id,
            "responder_vdc_id": self.responder_vdc_id,
            "terms_digest": self.terms.terms_digest,
            "initiator_signature": self.initiator_signature,
            "responder_signature": self.responder_signature,
            "prev_block_hash": self.prev_block_hash,
            "timestamp": self.timestamp,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    def compute_block_hash(self) -> str:
        """Compute SHA-256 hash of this block."""
        return hashlib.sha256(self.canonical_payload_bytes()).hexdigest()


class NegotiationLedgerAuditReport(BaseModel):
    """Audit report demonstrating cryptographic integrity of commercial negotiation."""

    session_id: str = Field(..., description="A2A negotiation session ID")
    total_blocks: int = Field(..., description="Number of blocks recorded")
    chain_intact: bool = Field(..., description="True if sequential hash continuity and signatures hold")
    integrity_error: str | None = Field(None, description="Error detail if chain is broken")
    final_contract_agreed: bool = Field(..., description="True if final_contract block exists and is dual-signed")
    initiator_did: str = Field(..., description="Corporate DID of initiating party")
    responder_did: str = Field(..., description="Corporate DID of responding party")
    blocks: list[DualSignedNegotiationBlock] = Field(default_factory=list, description="All blocks in session")
