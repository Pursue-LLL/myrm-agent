"""
[INPUT]: None
[OUTPUT]: Pydantic schemas and DTOs for verifiable provenance and physical isolation API
[POS]: myrm-agent-server/app/schemas/verifiable_provenance.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TenantSandboxContextDTO(BaseModel):
    """Client request context for tenant and physical volume resolution."""
    tenant_id: str = Field(..., description="Unique tenant or organization identifier")
    sandbox_id: str = Field(..., description="Dedicated sandbox container identifier")
    volume_id: str = Field(..., description="Dedicated persistent volume identifier")
    environment_token: str = Field(..., description="Cryptographically signed volume token")


class ResidencyProofRequest(BaseModel):
    """Request payload to verify and prove memory physical residency."""
    file_path: str = Field(..., description="Absolute or relative path to storage file")
    context: TenantSandboxContextDTO = Field(..., description="Dedicated sandbox environment context")
    extra_metadata: Optional[Dict[str, str]] = Field(default=None, description="Optional extra labels")


class ResidencyProofResponse(BaseModel):
    """Response containing transparent verifiable proof of physical residency."""
    tenant_id: str
    sandbox_id: str
    volume_id: str
    storage_path: str
    volume_mount_point: str
    file_inode: int
    content_sha256: str
    is_exclusive_volume: bool
    verified_at: datetime
    metadata: Dict[str, str]


class PhysicalPurgeRequest(BaseModel):
    """Request payload to execute true physical multi-pass overwrite and destruction."""
    file_path: str = Field(..., description="Target storage file to be physically destroyed")
    context: TenantSandboxContextDTO = Field(..., description="Dedicated sandbox environment context")


class DestructionReceiptResponse(BaseModel):
    """Cryptographically verifiable destruction receipt for right-to-be-forgotten audit."""
    receipt_id: str
    tenant_id: str
    sandbox_id: str
    volume_id: str
    purged_storage_path: str
    bytes_overwritten: int
    overwrite_passes: int
    status: str
    destruction_digest: str
    completed_at: datetime


class InspectPiiRequest(BaseModel):
    """Request payload to scan memory content for high-risk PII prior to persistence."""
    text: str = Field(..., description="Raw text proposed for long-term memory ingestion")


class PiiShieldResponse(BaseModel):
    """Inspection result indicating detected PII categories and sanitized text."""
    intercepted: bool
    detected_categories: List[str]
    sanitized_text: str
    masked_spans: List[str]
    has_child_privacy_violation: bool


class TokenGenerateRequest(BaseModel):
    """Request payload to generate a signed environment token for volume binding."""
    tenant_id: str
    sandbox_id: str
    volume_id: str


class TokenGenerateResponse(BaseModel):
    """Response containing the generated cryptographic token."""
    environment_token: str
    tenant_id: str
    sandbox_id: str
    volume_id: str
