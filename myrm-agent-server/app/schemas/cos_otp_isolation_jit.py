"""Pydantic schemas for CoS Sensitive OTP Isolation, Recovery Blackhole, and JIT Authorization API.

[POS] app/schemas/cos_otp_isolation_jit.py
[INPUT] pydantic
[OUTPUT] InspectMessageOtpRequest, InspectMessageOtpResponse, QuarantineOtpRequest, QuarantineOtpResponse, AuthorizeOtpUsageRequest, AuthorizeOtpUsageResponse, RetrieveOtpRequest, RetrieveOtpResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InspectMessageOtpRequest(BaseModel):
    """Request payload to inspect and redact dynamic OTPs from incoming messages."""

    model_config = ConfigDict(frozen=True)

    message_text: str = Field(..., description="Inbound communication text (email, SMS, IM)")


class InspectMessageOtpResponse(BaseModel):
    """Sanitized text output with redacted OTPs and detected reset indicators."""

    model_config = ConfigDict(frozen=True)

    original_text: str
    sanitized_text: str
    detected_otp_codes: list[str]
    redaction_count: int
    contains_password_reset_link: bool


class BlackholeCheckRequest(BaseModel):
    """Request payload to test URLs or text against password reset blackhole rules."""

    model_config = ConfigDict(frozen=True)

    target_text_or_url: str = Field(..., description="Content or URL to evaluate for blackhole lock")


class BlackholeCheckResponse(BaseModel):
    """Outcome of password recovery blackhole evaluation."""

    model_config = ConfigDict(frozen=True)

    is_blackholed: bool
    detected_links: list[str]
    reason: str
    human_intervention_required: bool


class IssueJitTicketRequest(BaseModel):
    """Request payload to issue a single-use intent-bound JIT authorization ticket."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Active session ID where user authorized action")
    target_domain: str = Field(..., description="Permitted target domain (e.g. checkout.merchant.com)")
    purpose: str = Field(..., description="Declared transactional purpose")
    otp_code: str = Field(..., description="Raw dynamic OTP code to be burn-after-reading injected")
    validity_seconds: int = Field(default=60, ge=10, le=300, description="Ticket lifespan in seconds")


class JitTicketResponse(BaseModel):
    """Issued ephemeral JIT ticket metadata."""

    model_config = ConfigDict(frozen=True)

    ticket_id: str
    session_id: str
    target_domain: str
    purpose: str
    issued_at: float
    expires_at: float
    consumed: bool


class ConsumeJitTicketRequest(BaseModel):
    """Request payload to consume and burn a JIT ticket."""

    model_config = ConfigDict(frozen=True)

    ticket_id: str
    target_domain: str = Field(..., description="Target domain attempting consumption")


class ConsumeJitTicketResponse(BaseModel):
    """Result of JIT ticket consumption."""

    model_config = ConfigDict(frozen=True)

    success: bool
    otp_code: str | None = None
    reason: str


class EvaluateQuotaRequest(BaseModel):
    """Request payload to assess quota consumption and calculate watermark warnings."""

    model_config = ConfigDict(frozen=True)

    used_units: float = Field(..., ge=0.0, description="Consumed token units or compute credits")
    max_units: float = Field(..., gt=0.0, description="Total allocated quota limit")
    fallback_model: str = Field(default="llama-3.1-8b-local", description="Designated offline fallback model")


class EvaluateQuotaResponse(BaseModel):
    """Quota assessment result with progressive watermark alerts."""

    model_config = ConfigDict(frozen=True)

    used_units: float
    max_units: float
    usage_ratio: float
    tier: str
    alert_message: str | None
    fallback_model_recommended: str | None
