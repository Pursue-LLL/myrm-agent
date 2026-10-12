"""Pydantic schemas for Mechanical Credential Isolation and Zero-Context Secret Replacement.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for secret ingestion, egress token injection, and atomic one-shot grants.

[POS]
- Server schemas. Exposes typed contracts for client-side masked token submission,
  egress-bound proxy substitution, and parameter-hash-bound operation grants.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class BoundSecretHandleDto(BaseModel):
    """Metadata DTO for an opaque secret reference handle."""

    model_config = ConfigDict(extra="forbid")

    handle_id: str = Field(..., description="Unique opaque reference ID (e.g. hnd_12345678)")
    secret_name: str = Field(..., description="Human-readable alias or purpose")
    placeholder: str = Field(..., description="Opaque template tag (e.g. {{SECRET_VAULT:hnd_...}})")
    allowed_host: str = Field(..., description="Whitelisted egress destination host")
    created_at: float = Field(default_factory=time.time, description="Unix timestamp of registration")


class IngestSecretRequest(BaseModel):
    """Payload to store a sensitive credential bound to an egress host."""

    model_config = ConfigDict(extra="forbid")

    secret_name: str = Field(..., description="Name or identifier of the secret (e.g. STRIPE_API_KEY)")
    secret_value: str = Field(..., description="Plaintext secret value to be securely vaulted")
    allowed_host: str = Field(..., description="Target egress host (e.g. api.stripe.com)")


class IngestSecretResponse(BaseModel):
    """Result after securely ingesting and isolating a secret."""

    model_config = ConfigDict(extra="forbid")

    handle: BoundSecretHandleDto = Field(..., description="Opaque reference handle safe for prompt context")
    message: str = Field("Secret securely ingested and bound to destination host", description="Status message")


class ResolveEgressRequest(BaseModel):
    """Request to replace placeholders with plaintext credentials at outbound dispatch."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., description="Outbound request payload or headers with placeholder tags")
    target_host: str = Field(..., description="Destination hostname for the outbound request")


class ResolveEgressResponse(BaseModel):
    """Result after egress substitution."""

    model_config = ConfigDict(extra="forbid")

    resolved_content: str = Field(..., description="Content with credentials injected for authorized host")
    replacements_count: int = Field(..., description="Number of replaced secret placeholders")
    target_host: str = Field(..., description="Target hostname verified against whitelist")
    authorized: bool = Field(..., description="Whether substitution was permitted")


class AtomicGrantDto(BaseModel):
    """DTO representing a one-shot atomic operation grant."""

    model_config = ConfigDict(extra="forbid")

    grant_id: str = Field(..., description="Unique grant identifier")
    operation_name: str = Field(..., description="Exact operation/job name authorized")
    payload_hash: str = Field(..., description="SHA-256 fingerprint of authorized parameters")
    status: str = Field(..., description="Lifecycle status: pending, granted, used, revoked, invalidated")
    created_at: float = Field(..., description="Timestamp of grant creation")
    expires_at: float = Field(..., description="Timestamp of grant expiration")


class CreateAtomicGrantRequest(BaseModel):
    """Request to create a one-shot grant for a sensitive operation."""

    model_config = ConfigDict(extra="forbid")

    operation_name: str = Field(..., description="Target sensitive operation name")
    payload: dict[str, str | int | float | bool | list[str]] = Field(
        ..., description="Exact parameters of the operation"
    )
    ttl_seconds: float = Field(default=180.0, description="Grant time-to-live in seconds")


class ConsumeAtomicGrantRequest(BaseModel):
    """Request to verify and consume a one-shot grant."""

    model_config = ConfigDict(extra="forbid")

    operation_name: str = Field(..., description="Operation being executed")
    payload: dict[str, str | int | float | bool | list[str]] = Field(
        ..., description="Current parameters being executed"
    )


class RejectAtomicGrantRequest(BaseModel):
    """Request to terminally revoke and close an operation grant."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="User denied operation", description="Reason for terminal rejection")
