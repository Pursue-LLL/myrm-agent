"""Schemas for Local Agent Tamper-Proof Action Ledger and Financial Sign-Off Gate.

[POS]
Defines data structures for:
1. Append-only tamper-evident local data access ledger (emails, invoices, credentials).
2. Egress data footprints and receipts (irreversible external fact tracking).
3. Human sign-off action surfaces, before-run plans, and delivery receipts (three-stage chain).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Literal

from pydantic import BaseModel, Field


class LocalActionAuditEntry(BaseModel):
    """Cryptographically chained entry recording an agent's access to sensitive local entities."""

    entry_id: str = Field(..., description="Unique UUID for this audit entry")
    agent_id: str = Field(..., description="ID of the agent performing the data operation")
    session_id: str | None = Field(None, description="Optional chat session ID")
    task_id: str | None = Field(None, description="Optional background or workflow task ID")
    timestamp_ns: int = Field(default_factory=time.time_ns, description="Nanosecond timestamp")
    target_entity_type: str = Field(
        ...,
        description="Type of sensitive entity, e.g. email, invoice, id_card, bank_card, credential, document",
    )
    target_entity_id: str = Field(..., description="Logical ID or path of the target entity")
    entity_hash: str = Field(..., description="SHA-256 hash of entity content for integrity proof")
    action: str = Field(..., description="Action taken: read, classify, extract, archive, draft_reply")
    intent_summary: str = Field(..., description="Human-readable explanation of why the agent accessed this data")
    operator_or_model: str = Field(..., description="Model identifier or system operator executing the action")
    prev_entry_hash: str = Field(..., description="SHA-256 hash of preceding entry in chain")
    entry_hash: str = Field(default="", description="SHA-256 digest of this entry payload")
    signature: str = Field(default="", description="HMAC-SHA256 signature certifying entry authenticity")

    def canonical_payload_bytes(self) -> bytes:
        """Produce deterministic canonical JSON bytes for hashing and signing."""
        payload: dict[str, str | int | None] = {
            "entry_id": self.entry_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "timestamp_ns": self.timestamp_ns,
            "target_entity_type": self.target_entity_type,
            "target_entity_id": self.target_entity_id,
            "entity_hash": self.entity_hash,
            "action": self.action,
            "intent_summary": self.intent_summary,
            "operator_or_model": self.operator_or_model,
            "prev_entry_hash": self.prev_entry_hash,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    def compute_hash(self) -> str:
        """Compute the SHA-256 hash of this entry's canonical content."""
        return hashlib.sha256(self.canonical_payload_bytes()).hexdigest()

    def sign(self, secret_key: str) -> str:
        """Sign canonical bytes with HMAC-SHA256."""
        mac = hmac.new(
            secret_key.encode("utf-8"),
            self.canonical_payload_bytes(),
            hashlib.sha256,
        )
        return mac.hexdigest()

    def verify_signature(self, secret_key: str) -> bool:
        """Verify entry signature against expected secret key."""
        if not self.signature:
            return False
        expected_sig = self.sign(secret_key)
        return hmac.compare_digest(self.signature, expected_sig)


class EgressFootprintReceipt(BaseModel):
    """Irreversible record of outbound network transmission."""

    receipt_id: str = Field(..., description="Unique receipt identifier")
    agent_id: str = Field(..., description="ID of the agent initiating the egress")
    session_id: str | None = Field(None, description="Associated session ID")
    task_id: str | None = Field(None, description="Associated task ID")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of egress transmission")
    target_host: str = Field(..., description="Destination hostname or IP")
    target_url: str = Field(..., description="Full target URL destination")
    method: str = Field(default="POST", description="HTTP method or protocol")
    content_summary: str = Field(..., description="Safe redaction/summary of outbound payload")
    sensitivity_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        default="HIGH",
        description="Data sensitivity classification",
    )
    taint_tags: list[str] = Field(default_factory=list, description="Taint tags such as pii, financial, secret")
    credential_redacted: bool = Field(default=False, description="Whether secrets were replaced before egress")
    approved_by_human: bool = Field(default=False, description="Whether this egress was approved by human sign-off")
    approval_id: str | None = Field(None, description="Referenced approval record ID if applicable")
    is_revocable: bool = Field(
        default=False,
        description="Honest disclosure: egressed external network facts cannot be revoked, only audited",
    )


class FinancialActionDetails(BaseModel):
    """Specific parameters for a financial payment or transfer action."""

    amount: float = Field(..., gt=0, description="Monetary transfer amount")
    currency: str = Field(default="USD", description="ISO currency code, e.g. USD, CNY, EUR")
    payee_account: str = Field(..., description="Masked or full destination account identifier")
    payee_name: str = Field(..., description="Recipient individual or vendor entity name")
    purpose: str = Field(..., description="Business purpose or invoice number reference")


class EmailActionDetails(BaseModel):
    """Specific parameters for an external email transmission."""

    recipients: list[str] = Field(..., min_length=1, description="Destination email addresses")
    cc: list[str] = Field(default_factory=list, description="Carbon copy recipients")
    subject: str = Field(..., description="Email subject line")
    body_preview: str = Field(..., description="Text preview or body snippet of the outgoing email")
    has_attachments: bool = Field(default=False, description="Whether files are attached")


class EndpointActionDetails(BaseModel):
    """Specific parameters for an external webhook or API invocation."""

    target_url: str = Field(..., description="Target API endpoint URL")
    method: str = Field(default="POST", description="HTTP request method")
    payload_summary: str = Field(..., description="Sanitized payload overview")


class ActionSurface(BaseModel):
    """Human-readable action surface revealing exact parameters before sign-off."""

    action_type: Literal["payment_transfer", "send_email", "external_webhook", "bulk_export"] = Field(
        ...,
        description="Category of high-impact action requiring human sign-off",
    )
    financial_details: FinancialActionDetails | None = Field(None, description="Details if payment_transfer")
    email_details: EmailActionDetails | None = Field(None, description="Details if send_email")
    endpoint_details: EndpointActionDetails | None = Field(None, description="Details if external_webhook")
    action_digest: str = Field(..., description="Cryptographic SHA-256 digest of deterministic action parameters")

    @classmethod
    def compute_digest(
        cls,
        action_type: str,
        details_json: str,
    ) -> str:
        """Compute deterministic digest for action surface."""
        raw = f"{action_type}:{details_json}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class BeforeRunPlan(BaseModel):
    """Before-run execution plan disclosed to human reviewer."""

    steps: list[str] = Field(..., min_length=1, description="Ordered steps planned for execution")
    risk_assessment: str = Field(..., description="Clear risk evaluation, e.g. irreversible funds disbursement")
    estimated_impact: str = Field(..., description="Scope of impact on assets, users, or external systems")
    fail_closed: bool = Field(default=True, description="Enforce strict rejection if sign-off fails or times out")


class DeliveryReceipt(BaseModel):
    """Execution receipt capturing external result to complete the three-stage chain."""

    delivery_receipt_id: str = Field(..., description="Unique receipt identifier")
    approval_id: str = Field(..., description="ID of the approved action")
    action_type: str = Field(..., description="Action type executed")
    external_reference_id: str | None = Field(None, description="External message_id, tx_hash, or order_id")
    delivery_status: Literal["DELIVERED", "SETTLED", "FAILED"] = Field(..., description="External outcome")
    completed_at: float = Field(default_factory=time.time, description="Unix timestamp of completion")
    response_digest: str = Field(..., description="SHA-256 hash of external response body")


class FinancialSignOffDraft(BaseModel):
    """Complete sign-off entity binding action surface, plan, approval state, and delivery receipt."""

    draft_id: str = Field(..., description="Unique draft identifier")
    agent_id: str = Field(..., description="Agent that drafted this action")
    session_id: str | None = Field(None, description="Originating chat session ID")
    task_id: str | None = Field(None, description="Originating task ID")
    action_surface: ActionSurface = Field(..., description="Revealed parameters and action digest")
    plan: BeforeRunPlan = Field(..., description="Before-run plan preview")
    status: Literal["DRAFT", "PENDING_SIGNOFF", "APPROVED", "REJECTED", "EXECUTED"] = Field(
        default="PENDING_SIGNOFF",
        description="Lifecycle state of the sign-off draft",
    )
    signoff_token: str | None = Field(None, description="Cryptographic token generated upon human sign-off")
    operator_id: str | None = Field(None, description="Human reviewer identifier who authorized the action")
    signed_at: float | None = Field(None, description="Timestamp of human sign-off")
    delivery_receipt: DeliveryReceipt | None = Field(None, description="Bound post-execution delivery receipt")
    created_at: float = Field(default_factory=time.time, description="Draft creation timestamp")


class PrivacyInspectorSummary(BaseModel):
    """Dashboard metrics summarizing agent local access and egress facts."""

    agent_id: str | None = Field(None, description="Filter agent ID or null for global")
    period: str = Field(default="today", description="Aggregation timeframe")
    total_sensitive_entities_read: int = Field(0, description="Total sensitive records accessed")
    entity_type_counts: dict[str, int] = Field(default_factory=dict, description="Counts by entity category")
    total_drafts_created: int = Field(0, description="Total outbound/financial drafts created")
    total_financial_interceptions: int = Field(0, description="Total financial actions intercepted for sign-off")
    total_pending_signoffs: int = Field(0, description="Currently pending sign-offs")
    total_egress_events: int = Field(0, description="Total egress requests recorded")
    top_egress_hosts: list[dict[str, str | int]] = Field(default_factory=list, description="Top contacted hosts")
    ledger_chain_healthy: bool = Field(True, description="Cryptographic audit hash chain integrity state")
