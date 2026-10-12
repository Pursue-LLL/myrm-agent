"""
[POS] app/schemas/request_secret.py
[INPUT] pydantic
[OUTPUT] Request-secret masked credential card request and response DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MaskedCredentialRefDTO(BaseModel):
    """Safe, transcript-friendly reference to an existing stored credential."""

    credential_id: str = Field(..., description="Unique opaque credential identifier")
    target_system: str = Field(..., description="Target system or service, e.g. github, aws, stripe")
    mask_preview: str = Field(..., description="Masked display fingerprint (e.g. ghp_****1234)")
    created_at: float = Field(..., description="Creation epoch timestamp")


class SecretRequestIntentDTO(BaseModel):
    """Agent's structured specification requesting a task-scoped secret."""

    target_system: str = Field(..., min_length=1, description="Target destination system (e.g. github, openai)")
    purpose_description: str = Field(..., min_length=1, description="Human-understandable justification")
    scope: str = Field(default="default", description="Requested access permission scope")
    ttl_seconds: int = Field(default=3600, ge=60, le=86400, description="Authorized credential time-to-live in seconds")


class CreateSecretCardRequestDTO(BaseModel):
    """Payload to initiate a new secret request card session."""

    agent_id: str = Field(..., min_length=1, description="Requesting agent identifier")
    task_id: str = Field(..., min_length=1, description="Associated task identifier")
    intent: SecretRequestIntentDTO = Field(..., description="Requested intent specifications")


class SecretCardSessionDTO(BaseModel):
    """Interactive card session state presented to user or channel."""

    card_id: str = Field(..., description="Unique secret card session ID")
    agent_id: str = Field(..., description="Requesting agent identifier")
    task_id: str = Field(..., description="Task or run identifier")
    intent: SecretRequestIntentDTO = Field(..., description="Requested intent specifications")
    status: str = Field(..., description="Current card status: pending, fulfilled, rejected, expired")
    masked_ref: MaskedCredentialRefDTO | None = Field(default=None, description="Resolved masked credential reference")
    rejection_reason: str | None = Field(default=None, description="Reason if user rejected request")
    created_at: float = Field(..., description="Session creation timestamp")
    expires_at: float = Field(..., description="Session expiration timestamp")


class SecretInputSubmissionDTO(BaseModel):
    """User submission providing either a newly inputted secret or selecting an existing masked credential."""

    raw_secret: str | None = Field(default=None, description="Raw plaintext secret (encrypted immediately upon receipt)")
    selected_credential_id: str | None = Field(
        default=None,
        description="ID of an existing saved credential selected for backfill",
    )
    extra_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Optional clean key-value metadata",
    )


class FulfillSecretCardRequestDTO(BaseModel):
    """Payload to fulfill an active secret card."""

    card_id: str = Field(..., description="Card session ID to fulfill")
    submission: SecretInputSubmissionDTO = Field(..., description="Submitted credentials or backfill reference")


class SanitizedSecretResultDTO(BaseModel):
    """Resolution payload safe for emitting to agent loop and transcript."""

    card_id: str = Field(..., description="Resolved card session identifier")
    target_system: str = Field(..., description="Target system identifier")
    mask_preview: str = Field(..., description="Masked fingerprint of secret")
    is_backfill: bool = Field(default=False, description="Whether credential was fulfilled via existing saved backfill")
    stored_safely: bool = Field(default=True, description="Whether secret was successfully stored in secure vault")
    transcript_safe_summary: str = Field(..., description="Transcript-safe narrative without raw secret exposure")


class RejectSecretCardRequestDTO(BaseModel):
    """Payload to reject an active secret card."""

    card_id: str = Field(..., description="Card session ID to reject")
    reason: str = Field(default="User declined to provide secret", description="Rejection reason")


class RegisterSavedCredentialRequestDTO(BaseModel):
    """Payload to register an existing credential in vault."""

    target_system: str = Field(..., min_length=1, description="Target system name")
    raw_secret: str = Field(..., min_length=4, description="Plaintext secret")
    credential_id: str | None = Field(default=None, description="Optional custom credential ID")
