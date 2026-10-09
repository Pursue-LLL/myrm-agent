"""Data transfer objects for Document Attachment Ownership & Lifecycle API.

[POS]
Defines Pydantic request and response schemas for document-owned attachments,
deferred physical reclaim sweeps, and legacy relationship migration.

[INPUT]
- typing, pydantic

[OUTPUT]
- AttachRequestDTO, AttachmentOwnershipItemDTO, DetachRequestDTO, DetachResponseDTO
- ReclaimAuditReportDTO, LegacyEntryDTO, MigrateRequestDTO, MigrationReportDTO, AttachmentStatsDTO
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AttachRequestDTO(BaseModel):
    """Client request to attach content to a document."""

    document_id: str = Field(min_length=1, description="Target document ID")
    file_name: str = Field(min_length=1, description="Attachment file name")
    mime_type: str = Field(default="application/octet-stream", description="MIME type of attachment")
    content_text: str | None = Field(default=None, description="UTF-8 plain text content if applicable")
    content_base64: str | None = Field(default=None, description="Base64 encoded binary content")


class AttachmentOwnershipItemDTO(BaseModel):
    """Authoritative document-owned attachment metadata response."""

    attachment_id: str
    document_id: str
    attachment_hash: str
    storage_key: str
    file_name: str
    mime_type: str
    byte_size: int
    created_at: float


class DetachRequestDTO(BaseModel):
    """Request to detach an attachment from a document."""

    document_id: str = Field(min_length=1, description="Parent document ID")
    attachment_id: str = Field(min_length=1, description="Attachment ID to detach")


class DetachResponseDTO(BaseModel):
    """Response indicating detachment status."""

    success: bool
    document_id: str
    attachment_id: str


class ReclaimAuditReportDTO(BaseModel):
    """Report from deterministic garbage collection sweep."""

    scanned_blobs: int
    reclaimed_blobs: int
    freed_bytes: int
    retained_blobs: int
    reclaimed_storage_keys: list[str]
    elapsed_ms: float


class LegacyEntryDTO(BaseModel):
    """Legacy attachment record for migration."""

    legacy_id: str
    attachment_hash: str
    file_name: str
    mime_type: str
    byte_size: int
    associated_document_ids: list[str] = Field(default_factory=list)


class MigrateRequestDTO(BaseModel):
    """Request to migrate legacy multi-associated entries to document ownership."""

    legacy_entries: list[LegacyEntryDTO] = Field(default_factory=list)
    blob_payloads_base64: dict[str, str] = Field(default_factory=dict)


class MigrationReportDTO(BaseModel):
    """Report produced when migrating legacy attachments."""

    total_scanned: int
    migrated_records: int
    dropped_orphans: int
    elapsed_ms: float


class AttachmentStatsDTO(BaseModel):
    """Overall attachment and storage health statistics."""

    total_documents: int
    total_attachment_rows: int
    total_storage_keys: int
    total_physical_bytes: int
    orphaned_unclaimed_keys: int
