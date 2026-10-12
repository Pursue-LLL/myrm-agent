"""
[POS] app/schemas/autonomous_signing_airgap.py
[INPUT] pydantic
[OUTPUT] Signing evaluation, Step-up HITL, Kill-switch, Quota config, and Metrics DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluateSigningRequestDTO(BaseModel):
    """Payload to request autonomous signing approval for a transaction."""

    tx_id: str = Field(..., description="Unique transaction proposal ID")
    recipient: str = Field(..., description="Destination recipient contract or wallet address")
    amount: float = Field(..., gt=0.0, description="Transaction monetary amount")
    currency: str = Field(default="USDC", description="Currency ticker symbol")
    chain_or_network: str = Field(default="base", description="Target blockchain or network identifier")
    call_data_summary: str = Field(default="", description="Human-readable summary of call signature and data")
    metadata: dict[str, str] = Field(default_factory=dict, description="Diagnostic tags from agent context")


class SigningVerdictResponseDTO(BaseModel):
    """Verdict output from the airgapped signing delegate."""

    decision: str = Field(..., description="Decision status: SILENT_AUTHORIZED, REQUIRE_HITL_STEP_UP, etc.")
    is_approved_to_sign: bool = Field(..., description="Whether transaction was signed and approved")
    signature_token: str | None = Field(default=None, description="Cryptographic signature mock if authorized")
    diagnostic_reason: str = Field(..., description="Explanatory audit message")
    tx_id: str = Field(..., description="Transaction proposal ID")
    remaining_daily_allowance: float = Field(..., description="Remaining expenditure capacity in active window")


class ApproveStepUpRequestDTO(BaseModel):
    """Payload for human operator to approve an escalated transaction."""

    tx_id: str = Field(..., description="Pending transaction identifier")
    approver_note: str = Field(default="Human Operator Approved", description="Audit note recorded by approver")


class RejectStepUpRequestDTO(BaseModel):
    """Payload for human operator to reject an escalated transaction."""

    tx_id: str = Field(..., description="Pending transaction identifier")
    reason: str = Field(default="Operator Rejected", description="Rejection reason")


class TriggerKillSwitchRequestDTO(BaseModel):
    """Payload to engage emergency wallet freeze."""

    reason: str = Field(default="Emergency Freeze Triggered", description="Audit reason for activating kill-switch")


class KillSwitchStatusResponseDTO(BaseModel):
    """Current posture of the emergency airgap kill-switch."""

    is_kill_switch_active: bool = Field(..., description="Whether emergency freeze is currently active")
    kill_switch_reason: str = Field(default="", description="Reason for active freeze")


class UpdateQuotaConfigRequestDTO(BaseModel):
    """Configuration to update signing quotas and recipient whitelist."""

    single_tx_limit: float = Field(..., gt=0.0, description="Max amount for silent one-off transaction")
    daily_cumulative_limit: float = Field(..., gt=0.0, description="Max cumulative amount permitted per window")
    trusted_recipients: list[str] = Field(
        default_factory=list,
        description="Allowed destination recipient addresses (empty permits any address within limits)",
    )


class QuotaConfigResponseDTO(BaseModel):
    """Details of active signing quota rules and expenditure."""

    single_tx_limit: float = Field(..., description="Max silent single transaction limit")
    daily_cumulative_limit: float = Field(..., description="Max daily cumulative limit")
    trusted_recipients: list[str] = Field(..., description="Whitelisted recipient addresses")
    current_daily_spent: float = Field(..., description="Accumulated expenditure in current cycle")
    remaining_daily_allowance: float = Field(..., description="Unspent quota allowance remaining")


class WalletAirgapMetricsResponseDTO(BaseModel):
    """Operational metric counters for the autonomous signing airgap sandbox."""

    evaluations_total: int = Field(..., description="Total signing evaluations conducted")
    silent_signed_total: int = Field(..., description="Total transactions silently signed")
    hitl_stepped_up_total: int = Field(..., description="Total transactions stepped up for human review")
    rejected_quota_total: int = Field(..., description="Total rejections due to budget limits")
    rejected_untrusted_total: int = Field(..., description="Total rejections due to unwhitelisted recipient")
    kill_switch_blocked_total: int = Field(..., description="Total requests blocked by emergency kill-switch")
