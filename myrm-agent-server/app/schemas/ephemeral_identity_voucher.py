"""
[POS] app/schemas/ephemeral_identity_voucher.py
[INPUT] pydantic
[OUTPUT] EphemeralIdentity DTOs, MerchantLockedVoucher DTOs, AuditTrail DTOs, Metrics DTOs

Pydantic schemas for Dynamic Ephemeral Identity & Verifiable Audit Trail Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IssueIdentityRequestDTO(BaseModel):
    """Payload to dynamically provision an ephemeral sub-identity."""

    agent_id: str = Field(..., description="Unique requesting agent identifier")
    task_id: str = Field(..., description="Active task context or execution trace ID")
    allowed_scopes: list[str] = Field(
        default_factory=list,
        description="Explicit capability scopes granted to this ephemeral identity",
    )
    ttl_seconds: float = Field(
        default=600.0,
        ge=1.0,
        le=3600.0,
        description="Lifespan window in seconds before self-destruction",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Non-sensitive diagnostic key-value pairs",
    )


class EphemeralIdentityResponseDTO(BaseModel):
    """Details of provisioned ephemeral identity."""

    identity_id: str = Field(..., description="Unique ephemeral identity ID")
    agent_id: str = Field(..., description="Agent ID")
    task_id: str = Field(..., description="Task ID")
    allowed_scopes: list[str] = Field(..., description="Authorized scopes")
    ephemeral_token: str = Field(..., description="Secret high-entropy bearer token")
    created_at_epoch: float = Field(..., description="Creation epoch timestamp")
    expires_at_epoch: float = Field(..., description="Expiration epoch timestamp")
    status: str = Field(..., description="Lifecycle status: ACTIVE, REVOKED, EXPIRED, CONSUMED")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata tags")


class VerifyIdentityRequestDTO(BaseModel):
    """Payload to verify an ephemeral identity token."""

    identity_id: str = Field(..., description="Ephemeral identity ID")
    ephemeral_token: str = Field(..., description="Bearer token to verify")
    required_scope: str | None = Field(
        default=None,
        description="Optional specific scope required for the operation",
    )


class VerifyIdentityResponseDTO(BaseModel):
    """Outcome of verifying ephemeral identity token."""

    is_valid: bool = Field(..., description="Whether identity is valid, active, and authorized")
    status: str = Field(..., description="Current status of the identity")
    diagnostic_reason: str = Field(..., description="Explanation of verification verdict")


class RevokeIdentityRequestDTO(BaseModel):
    """Payload to revoke an ephemeral identity."""

    reason: str = Field(default="Administrative revocation", description="Revocation reason")


class IssueVoucherRequestDTO(BaseModel):
    """Payload to generate a domain-locked disposable payment voucher."""

    identity_id: str = Field(..., description="Associated ephemeral identity ID")
    target_merchant_domain: str = Field(
        ...,
        description="Target merchant host or URL strictly locked for redemption",
    )
    max_authorized_amount: float = Field(
        ...,
        gt=0.0,
        description="Monetary upper cap authorized for this single-use voucher",
    )
    currency: str = Field(default="USD", description="Currency ISO code")
    ttl_seconds: float = Field(
        default=600.0,
        ge=10.0,
        le=3600.0,
        description="Voucher validity window in seconds",
    )


class MerchantLockedVoucherResponseDTO(BaseModel):
    """Details of issued merchant-locked payment voucher."""

    voucher_id: str = Field(..., description="Unique voucher ID")
    identity_id: str = Field(..., description="Associated identity ID")
    target_merchant_domain: str = Field(..., description="Bound merchant domain")
    max_authorized_amount: float = Field(..., description="Authorized spending ceiling")
    currency: str = Field(..., description="Currency code")
    single_use_token: str = Field(..., description="One-time redemption token")
    created_at_epoch: float = Field(..., description="Creation epoch timestamp")
    expires_at_epoch: float = Field(..., description="Expiration epoch timestamp")
    status: str = Field(..., description="Voucher status: ISSUED, REDEEMED, VOIDED, EXPIRED, etc.")
    redeemed_amount: float = Field(default=0.0, description="Amount spent if redeemed")
    merchant_order_ref: str | None = Field(default=None, description="External order reference")


class RedeemVoucherRequestDTO(BaseModel):
    """Payload to redeem a single-use payment voucher."""

    voucher_id: str = Field(..., description="Voucher ID")
    single_use_token: str = Field(..., description="Redemption secret token")
    request_domain: str = Field(..., description="Actual domain initiating redemption request")
    requested_amount: float = Field(..., gt=0.0, description="Exact amount to be billed")
    merchant_order_ref: str | None = Field(
        default=None, description="Optional merchant order or invoice ID"
    )


class RedeemVoucherResponseDTO(BaseModel):
    """Outcome of attempting to redeem a payment voucher."""

    is_success: bool = Field(..., description="Whether redemption succeeded")
    status: str = Field(..., description="Resulting status of the voucher")
    diagnostic_reason: str = Field(..., description="Justification or error details")
    voucher: MerchantLockedVoucherResponseDTO | None = Field(
        default=None, description="Updated voucher record if found"
    )


class VoidVoucherRequestDTO(BaseModel):
    """Payload to void an unspent voucher."""

    reason: str = Field(default="Administrative void", description="Voiding rationale")


class RecordAuditPhaseRequestDTO(BaseModel):
    """Payload to record one of the four closed-loop audit phases."""

    task_id: str = Field(..., description="Autonomous task context identifier")
    phase: str = Field(
        ...,
        description="Audit phase: USER_INTENT, CREDENTIAL_GRANT, EXECUTION_SNAPSHOT, SETTLEMENT_RECEIPT",
    )
    summary: str = Field(..., description="Human-readable event summary")
    structured_payload: dict[str, str] = Field(
        default_factory=dict,
        description="Structured key-value parameters for cryptographic hashing",
    )


class AuditEventResponseDTO(BaseModel):
    """Immutable chained audit log record."""

    event_id: str = Field(..., description="Unique audit event ID")
    task_id: str = Field(..., description="Task identifier")
    phase: str = Field(..., description="Phase identifier")
    timestamp_epoch: float = Field(..., description="Epoch timestamp")
    payload_hash: str = Field(..., description="SHA-256 digest of payload")
    raw_summary: str = Field(..., description="Event summary")
    parent_hash: str | None = Field(default=None, description="Hash of preceding record")
    node_hash: str = Field(..., description="Merkle leaf node hash")


class VerifyAuditTrailResponseDTO(BaseModel):
    """Verification outcome of task audit trail integrity."""

    task_id: str = Field(..., description="Task ID")
    is_valid: bool = Field(..., description="Whether the cryptographic chain is unbroken")
    diagnostic_reason: str = Field(..., description="Verification diagnostics")
    merkle_root: str | None = Field(default=None, description="Computed Merkle Root digest")


class AuditProofBundleResponseDTO(BaseModel):
    """Export package containing full audit trail and Merkle proof."""

    task_id: str = Field(..., description="Task ID")
    merkle_root: str = Field(..., description="Merkle root digest")
    phases_included: list[str] = Field(..., description="List of recorded phases")
    events: list[AuditEventResponseDTO] = Field(..., description="Ordered list of events")
    verification_success: bool = Field(..., description="Whether bundle verification succeeded")
    exported_at_epoch: float = Field(..., description="Export timestamp")


class EphemeralIdentityMetricsResponseDTO(BaseModel):
    """Aggregated operational metrics for identity, voucher, and audit systems."""

    identities_issued_total: int = Field(..., description="Total identities issued")
    identities_revoked_total: int = Field(..., description="Total identities revoked")
    identities_expired_total: int = Field(..., description="Total identities expired")
    vouchers_issued_total: int = Field(..., description="Total vouchers issued")
    vouchers_redeemed_total: int = Field(..., description="Total vouchers redeemed")
    vouchers_rejected_total: int = Field(..., description="Total vouchers rejected")
    audit_events_recorded_total: int = Field(..., description="Total audit events recorded")
