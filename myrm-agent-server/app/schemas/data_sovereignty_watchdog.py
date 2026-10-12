"""
[POS] app/schemas/data_sovereignty_watchdog.py
[INPUT] pydantic, enum
[OUTPUT] SovereigntySealLevelResponse, ProactivityValueLevelResponse, HighStakesActionTypeResponse, SovereigntySealManifestResponse, SubIntrusiveNotificationCardResponse, HighStakesConsentTicketResponse, IssueSovereigntySealRequest, VerifySovereigntySealRequest, VerifySovereigntySealResponse, EvaluateSuggestionRequest, CreateConsentTicketRequest, ConsentDecisionRequest, DataSovereigntyWatchdogMetricsResponse

Pydantic schemas for Private Sandbox Data Sovereignty & Sub-Intrusive Watchdog Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SovereigntySealLevelResponse(StrEnum):
    """Enforceable storage isolation guarantee."""

    LOCAL_AIRGAPPED = "LOCAL_AIRGAPPED"
    PRIVATE_SANDBOX_VOLUME = "PRIVATE_SANDBOX_VOLUME"
    VERIFIED_ENCRYPTED = "VERIFIED_ENCRYPTED"


class ProactivityValueLevelResponse(StrEnum):
    """Filter level for proactive suggestions."""

    TRIVIAL_NOISE = "TRIVIAL_NOISE"
    MODERATE_SUGGESTION = "MODERATE_SUGGESTION"
    HIGH_VALUE_ALERT = "HIGH_VALUE_ALERT"
    CRITICAL_DEADLINE = "CRITICAL_DEADLINE"


class HighStakesActionTypeResponse(StrEnum):
    """High-stakes financial or account mutation action requiring mandatory human consent."""

    SUBSCRIPTION_CANCEL = "SUBSCRIPTION_CANCEL"
    REFUND_DISPUTE = "REFUND_DISPUTE"
    PAYMENT_METHOD_UPDATE = "PAYMENT_METHOD_UPDATE"
    BALANCE_TRANSFER = "BALANCE_TRANSFER"


class SovereigntySealManifestResponse(BaseModel):
    """Immutable proof that financial receipts and email tokens remain strictly within private sandbox."""

    seal_id: str = Field(..., description="Unique sovereignty seal ID")
    storage_target: str = Field(..., description="Target database or storage path")
    seal_level: SovereigntySealLevelResponse = Field(..., description="Storage isolation level")
    central_cloud_zero_retention: bool = Field(
        ..., description="True if central cloud retention is strictly zero"
    )
    volume_mount_path: str = Field(..., description="Physical sandbox volume mount path")
    created_at: float = Field(..., description="Epoch issuance timestamp")
    checksum: str = Field(..., description="Cryptographic SHA-256 seal integrity checksum")


class SubIntrusiveNotificationCardResponse(BaseModel):
    """Non-intrusive notification card emitted only when value surpasses anti-annoyance thresholds."""

    card_id: str = Field(..., description="Unique notification card ID")
    title: str = Field(..., description="Alert card title")
    potential_savings_cents: int = Field(..., ge=0, description="Potential savings in cents")
    deadline_epoch: float | None = Field(default=None, description="Expiration or charge epoch")
    value_level: ProactivityValueLevelResponse = Field(..., description="Classified value level")
    is_suppressed: bool = Field(..., description="True if suppressed by watchdog filter")
    message: str = Field(..., description="Detailed high-density message content")
    service_name: str = Field(..., description="Associated external vendor or service")


class HighStakesConsentTicketResponse(BaseModel):
    """One-time ticket locking an automated financial/account mutation until human approval."""

    ticket_id: str = Field(..., description="Unique consent ticket ID")
    action_type: HighStakesActionTypeResponse = Field(..., description="Operation category")
    service_name: str = Field(..., description="Target service name")
    financial_impact_cents: int = Field(..., ge=0, description="Estimated monetary impact")
    payload_summary: str = Field(..., description="Readable summary of action payload")
    is_approved: bool = Field(default=False, description="Whether operator approved action")
    is_denied: bool = Field(default=False, description="Whether operator denied action")
    created_at: float = Field(..., description="Epoch ticket creation timestamp")


class IssueSovereigntySealRequest(BaseModel):
    """Payload to issue a private volume data sovereignty seal."""

    storage_target: str = Field(..., min_length=1, description="Database or storage location")
    volume_mount_path: str = Field(..., min_length=1, description="Mounted private volume path")
    seal_level: SovereigntySealLevelResponse = Field(
        default=SovereigntySealLevelResponse.PRIVATE_SANDBOX_VOLUME,
        description="Isolation guarantee level",
    )


class VerifySovereigntySealRequest(BaseModel):
    """Payload to verify an issued sovereignty seal."""

    seal_id: str = Field(..., min_length=1, description="Seal ID to verify")


class VerifySovereigntySealResponse(BaseModel):
    """Verification outcome of sovereignty seal."""

    seal_id: str = Field(..., description="Seal identifier")
    is_valid: bool = Field(..., description="True if cryptographic checksum is intact")


class EvaluateSuggestionRequest(BaseModel):
    """Payload to evaluate background inspection finding against anti-annoyance thresholds."""

    title: str = Field(..., min_length=1, description="Suggestion title")
    service_name: str = Field(..., min_length=1, description="Associated service")
    potential_savings_cents: int = Field(..., ge=0, description="Potential savings amount in cents")
    deadline_epoch: float | None = Field(default=None, description="Optional deadline epoch")
    message: str = Field(default="", description="Suggestion message text")


class CreateConsentTicketRequest(BaseModel):
    """Payload to lock a high-stakes financial action behind an operator consent ticket."""

    action_type: HighStakesActionTypeResponse = Field(..., description="High-stakes action type")
    service_name: str = Field(..., min_length=1, description="Target service name")
    financial_impact_cents: int = Field(..., ge=0, description="Monetary impact in cents")
    payload_summary: str = Field(..., min_length=1, description="Summary of mutation payload")


class ConsentDecisionRequest(BaseModel):
    """Payload to authorize or reject a pending consent ticket."""

    ticket_id: str = Field(..., min_length=1, description="Consent ticket ID")


class DataSovereigntyWatchdogMetricsResponse(BaseModel):
    """Cumulative operational metrics for data sovereignty and watchdog suite."""

    sovereignty_seals_issued_total: int = Field(..., ge=0)
    proactive_scans_total: int = Field(..., ge=0)
    noise_suppressed_total: int = Field(..., ge=0)
    high_value_alerts_emitted_total: int = Field(..., ge=0)
    high_stakes_actions_blocked_total: int = Field(..., ge=0)
    high_stakes_consents_approved_total: int = Field(..., ge=0)
    high_stakes_consents_denied_total: int = Field(..., ge=0)
