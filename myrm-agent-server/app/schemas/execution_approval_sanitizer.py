"""
[POS] app/schemas/execution_approval_sanitizer.py
[INPUT] pydantic
[OUTPUT] Execution approval secret redaction request/response DTOs, findings, and metrics schemas
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ApprovalSanitizeRequestDTO(BaseModel):
    """Payload to request sensitive credential redaction on an approval command or text."""

    request_id: str = Field(..., description="Unique approval request identifier")
    session_id: str = Field(..., description="Active conversational session ID")
    raw_command_or_text: str = Field(..., description="Raw command text or prompt potentially containing secrets")
    channel_target: str = Field(default="webui", description="Presentation target: webui, desktop, slack, feishu")
    metadata: dict[str, str] = Field(default_factory=dict, description="Diagnostic tags from agent context")


class RedactionFindingDTO(BaseModel):
    """Diagnostic detail of a single credential redacted from presentation."""

    secret_type: str = Field(..., description="Classification category of secret")
    start_index: int = Field(..., description="Start character index in original string")
    end_index: int = Field(..., description="End character index in original string")
    matched_preview: str = Field(..., description="Masked preview of matched credential")
    placeholder: str = Field(..., description="In-band redaction placeholder substituted")


class ApprovalSanitizeResponseDTO(BaseModel):
    """Result of sanitizing approval text for safe presentation across client channels."""

    request_id: str = Field(..., description="Request identifier")
    session_id: str = Field(..., description="Session identifier")
    sanitized_text: str = Field(..., description="Safe presentation text with credentials masked")
    redactions_count: int = Field(..., description="Number of sensitive credentials masked")
    detected_secret_types: list[str] = Field(..., description="Secret categories detected and sanitized")
    findings: list[RedactionFindingDTO] = Field(..., description="Detailed occurrences of redactions")
    badge_summary: str = Field(..., description="Audit badge describing security posture of presentation")


class QuickSanitizeRequestDTO(BaseModel):
    """Simplified payload for quick string sanitization without session context."""

    text: str = Field(..., description="Raw string to sanitize")


class QuickSanitizeResponseDTO(BaseModel):
    """Output from quick string sanitization."""

    sanitized_text: str = Field(..., description="Cleaned string with masked secrets")
    redactions_count: int = Field(..., description="Number of sensitive credentials masked")
    detected_secret_types: list[str] = Field(..., description="Secret categories detected")
    badge_summary: str = Field(..., description="Audit summary")


class SanitizerMetricsResponseDTO(BaseModel):
    """Cumulative telemetry metrics for execution approval secret redaction."""

    payloads_evaluated_total: int = Field(..., description="Total command payloads evaluated")
    clean_payloads_total: int = Field(..., description="Total payloads found without sensitive credentials")
    redacted_payloads_total: int = Field(..., description="Total payloads where sensitive secrets were masked")
    total_secrets_redacted_count: int = Field(..., description="Total individual secrets redacted across all payloads")
