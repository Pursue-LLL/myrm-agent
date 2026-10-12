"""
[POS] app/schemas/confidential_payment_sandbox.py
[INPUT] pydantic
[OUTPUT] Confidential VM hardware isolation & virtual card payment DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VerifyEnclaveRequestDTO(BaseModel):
    """Payload to verify cryptographic remote attestation proof."""

    enclave_id: str = Field(..., description="Unique enclave identifier")
    platform_type: str = Field(
        default="sev_snp",
        description="Platform architecture: sev_snp, tdx, emulated",
    )
    measurement_sha256: str = Field(
        default="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        description="Hardware measurement hash",
    )


class ConfidentialEnclaveAttestationDTO(BaseModel):
    """Cryptographic attestation report indicating hardware memory encryption."""

    enclave_id: str = Field(..., description="Enclave identifier")
    platform_type: str = Field(..., description="Platform architecture")
    status: str = Field(..., description="Attestation verification status")
    measurement_sha256: str = Field(..., description="Measurement SHA256")
    attested_at: float = Field(..., description="Attestation timestamp")
    is_memory_encrypted: bool = Field(..., description="Whether memory is encrypted")
    diagnostic: str = Field(..., description="Attestation diagnostic outcome")


class IssueVirtualCardRequestDTO(BaseModel):
    """Payload to request a blind disposable virtual payment card."""

    spending_limit: float = Field(..., description="Maximum allowed charge amount")
    currency: str = Field(default="USD", description="Currency code (USD, EUR, CNY)")
    validity_seconds: float = Field(default=3600.0, description="Card TTL in seconds")
    hitl_threshold: float | None = Field(
        default=None, description="Optional custom threshold triggering HITL approval"
    )


class SingleUseVirtualCardDTO(BaseModel):
    """Metadata of a blind disposable virtual card token."""

    card_token: str = Field(..., description="Opaque card token safe for agent context")
    masked_card_number: str = Field(..., description="Masked card number for UI preview")
    currency: str = Field(..., description="Currency code")
    spending_limit: float = Field(..., description="Maximum allowed charge amount")
    amount_spent: float = Field(..., description="Actual amount charged")
    status: str = Field(..., description="Card status: active, redeemed, expired, cancelled")
    created_at: float = Field(..., description="Creation timestamp")
    expires_at: float = Field(..., description="Expiration timestamp")
    requires_hitl: bool = Field(..., description="Whether user confirmation is mandated")


class VirtualCardPaymentRequestDTO(BaseModel):
    """Payment transaction request submitted by autonomous agent."""

    card_token: str = Field(..., description="Blind virtual card token")
    amount: float = Field(..., description="Charge amount")
    currency: str = Field(default="USD", description="Currency code")
    merchant_name: str = Field(..., description="Merchant name")
    item_description: str = Field(..., description="Description of goods or services")
    idempotency_key: str = Field(..., description="Idempotent transaction key")
    confirmed_by_user: bool = Field(default=False, description="User HITL confirmation status")


class VirtualCardPaymentReceiptDTO(BaseModel):
    """Settlement outcome for a single-use virtual card charge."""

    receipt_id: str = Field(..., description="Unique receipt identifier")
    card_token: str = Field(..., description="Virtual card token")
    charged_amount: float = Field(..., description="Amount successfully charged")
    currency: str = Field(..., description="Currency code")
    is_success: bool = Field(..., description="Whether payment settled")
    status: str = Field(..., description="Settlement status code")
    merchant_name: str = Field(..., description="Merchant charged")
    requires_hitl_escalation: bool = Field(..., description="Whether transaction needs user approval")
    message: str = Field(..., description="Diagnostic details")


class ScanMessageRequestDTO(BaseModel):
    """Content inspected by ingress prompt injection or egress exfiltration sentinels."""

    content: str = Field(..., description="Raw message content to inspect")


class DualSentinelScanResultDTO(BaseModel):
    """Inspection outcome of bidirectional sentinel."""

    direction: str = Field(..., description="Inspection direction: ingress or egress")
    is_blocked: bool = Field(..., description="Whether threat was detected and blocked")
    detected_threats: list[str] = Field(..., description="List of detected threat patterns")
    sanitized_content: str = Field(..., description="Cleaned or masked payload")
    diagnostic: str = Field(..., description="Diagnostic summary")


class ChannelAccessCheckRequestDTO(BaseModel):
    """Payload to assert access to external sensitive service channel."""

    channel_name: str = Field(..., description="External channel name (e.g. work_email, drive)")
    action_type: str = Field(..., description="Action attempted: read or write")
    fence_mode: str = Field(default="read_only", description="Fence mode: read_only or elevated_write_permitted")


class ChannelAccessCheckResponseDTO(BaseModel):
    """Outcome of channel read-only barrier check."""

    allowed: bool = Field(..., description="Whether access is allowed")
    reason: str = Field(..., description="Explanation for access resolution")


class ConfidentialPaymentMetricsDTO(BaseModel):
    """Operational telemetry metrics for enclaves and virtual cards."""

    attestations_verified_total: int = Field(..., description="Total enclaves attested")
    cards_issued_total: int = Field(..., description="Total virtual cards issued")
    payments_processed_total: int = Field(..., description="Total payment charges attempted")
    hitl_escalations_total: int = Field(..., description="Total charges requiring HITL approval")
    ingress_injections_blocked_total: int = Field(..., description="Total prompt injections blocked")
    egress_leaks_prevented_total: int = Field(..., description="Total card/key leaks prevented")
