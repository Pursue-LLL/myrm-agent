"""Pydantic schemas for Local-First Zero-Leak Vault and Zero-Knowledge E2EE Sharing Gateway API.

[INPUT]
Standard library datetime, pydantic BaseModel and Field.

[OUTPUT]
DlpRedactionMatchResponse, DlpSanitizeRequest, DlpSanitizeResponse, VaultItemCreateRequest,
VaultItemResponse, ZeroKnowledgeShareCreateRequest, ZeroKnowledgeShareResponse,
ZeroKnowledgeShareAccessResponse.

[POS]
Schema definitions for client-side encryption vault and E2EE sharing data transfer contracts.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DlpRedactionMatchResponse(BaseModel):
    """Individual sensitive element detected and sanitized by DLP scanner."""

    category: str
    original_snippet: str
    redacted_snippet: str
    start: int
    end: int


class DlpSanitizeRequest(BaseModel):
    """Payload to scan and sanitize content through the in-situ DLP pipeline."""

    content: str = Field(..., description="Raw text or artifact content to sanitize")
    enable_price_redaction: bool = Field(
        default=True, description="Whether to mask commercial pricing or quotes"
    )


class DlpSanitizeResponse(BaseModel):
    """Outcome of transparent in-situ DLP sanitization."""

    original_length: int
    redacted_length: int
    total_redactions: int
    categories_found: list[str]
    matches: list[DlpRedactionMatchResponse]
    sanitized_content: str


class RegisterLocalArtifactRequest(BaseModel):
    """Payload to register an artifact under the local-first physical storage invariant."""

    artifact_id: str = Field(..., description="Unique artifact identifier")
    title: str = Field(..., description="Human-readable title or presentation name")
    local_path: str = Field(..., description="Local physical filesystem path")
    content: str = Field(..., description="Artifact payload content")
    storage_mode: str = Field(
        default="local_first_disk",
        description="Storage classification: 'local_first_disk', 'sandbox_volume', 'encrypted_collaborative'",
    )


class LocalArtifactResponse(BaseModel):
    """Metadata record for a locally stored artifact with zero-cloud sync invariant."""

    artifact_id: str
    title: str
    local_path: str
    storage_mode: str
    is_cloud_synced: bool
    content_hash: str
    created_at: datetime
    updated_at: datetime


class CreateE2eeShareRequest(BaseModel):
    """Payload to create a zero-knowledge E2EE encrypted share envelope."""

    artifact_id: str = Field(..., description="Associated artifact identifier")
    plaintext_content: str = Field(..., description="Plaintext content to be DLP-sanitized and encrypted")
    ttl_seconds: int = Field(default=86400, ge=60, le=2592000, description="Share TTL in seconds")
    enable_dlp_sanitization: bool = Field(
        default=True, description="Whether to run transparent in-situ DLP sanitization before encryption"
    )


class E2eeShareResponse(BaseModel):
    """Zero-knowledge encrypted share envelope metadata."""

    share_id: str
    artifact_id: str
    ciphertext_b64: str
    nonce_b64: str
    salt_b64: str
    key_hash: str
    dlp_audit_passed: bool
    client_key_b64: str
    share_url_fragment: str
    expires_at: datetime
    created_at: datetime


class DecryptE2eeShareRequest(BaseModel):
    """Request payload to decrypt an E2EE envelope using client-held symmetric key."""

    client_key_b64: str = Field(..., description="Base64 encoded 256-bit AES-GCM symmetric key")


class DecryptE2eeShareResponse(BaseModel):
    """Decrypted plaintext content result."""

    share_id: str
    decrypted_content: str
    dlp_audit_passed: bool
