"""Pydantic schemas for Inbound Zero-Trust Quarantine & Redaction.

[INPUT]
- Web requests inspecting inbound channel messages or requesting human release of quarantined secrets.

[OUTPUT]
- Serialized detection outcomes, safe redacted content, quarantine metadata, and released payloads.

[POS]
- Server-side DTO contracts for inbound credential isolation and physical quarantine.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InspectInboundMessageRequest(BaseModel):
    """Request payload to sniff and quarantine inbound message."""

    content: str = Field(description="Raw inbound message body")
    channel_type: str = Field(
        default="email", description="Source channel type (email, im, webhook)"
    )
    sender: str = Field(default="", description="Sender address or identifier")
    recipient: str = Field(default="", description="Recipient address or identifier")
    ttl_seconds: float = Field(
        default=900.0, ge=1.0, le=86400.0, description="Quarantine TTL in seconds (default 15m)"
    )


class InspectInboundMessageResponse(BaseModel):
    """Result of sniffing and zero-trust redacting an inbound message."""

    is_quarantined: bool = Field(description="True if sensitive credentials were intercepted")
    detected_risks: list[str] = Field(
        default_factory=list, description="Categories of intercepted credentials"
    )
    safe_content: str = Field(description="Sanitized content safe for LLM context")
    quarantine_id: str | None = Field(
        default=None, description="Physical vault quarantine identifier"
    )
    release_card_url: str | None = Field(
        default=None, description="URL for human release card view"
    )
    expires_at: float | None = Field(
        default=None, description="Timestamp when quarantine entry will be purged"
    )


class QuarantineRecordMetadataDto(BaseModel):
    """Non-sensitive metadata describing a quarantined message."""

    quarantine_id: str = Field(description="Quarantine identifier")
    channel_type: str = Field(description="Channel type")
    sender: str = Field(description="Sender identifier")
    recipient: str = Field(description="Recipient identifier")
    detected_risks: list[str] = Field(description="Detected credential risks")
    status: str = Field(description="Current quarantine status (ACTIVE/RELEASED/EXPIRED)")
    created_at: float = Field(description="Creation unix timestamp")
    expires_at: float = Field(description="Expiration unix timestamp")


class ReleaseQuarantineResponse(BaseModel):
    """Decrypted secret payload presented strictly to authorized human users."""

    quarantine_id: str = Field(description="Quarantine identifier")
    detected_risks: list[str] = Field(description="Detected credential risks")
    original_content: str = Field(description="Decrypted original message content")
    released_at: float = Field(description="Release unix timestamp")


class PurgeQuarantineResponse(BaseModel):
    """Summary of purged expired quarantine records."""

    purged_count: int = Field(description="Number of destroyed expired entries")
