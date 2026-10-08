"""Data transfer objects for Durable Revision & Concurrent Writes API.

[POS]
Defines Pydantic request and response schemas for memory concurrent writes,
typed change receipts, point-in-time MVCC snapshot reads, and safe rollbacks.

[INPUT]
- typing, pydantic

[OUTPUT]
- WritePayloadDTO, ChangeReceiptDTO, SnapshotReadViewDTO
- RollbackRequestDTO, RetractRequestDTO, DurableRevisionStatsDTO
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WritePayloadDTO(BaseModel):
    """Client write mutation request payload."""

    key: str = Field(min_length=1, description="Target document or memory page key")
    content: str = Field(description="Content text payload")
    tags: dict[str, str] = Field(default_factory=dict, description="Metadata tags")
    expected_revision: int | None = Field(default=None, description="Optional optimistic concurrency check")
    request_id: str | None = Field(default=None, description="Client idempotency key")


class ChangeReceiptDTO(BaseModel):
    """Authoritative typed change receipt."""

    receipt_id: str
    key: str
    status: str
    canonical_revision: int
    timestamp: float
    pending_error: str | None = None
    checksum_crc32: int = 0
    metadata: dict[str, str] = Field(default_factory=dict)


class SnapshotReadViewDTO(BaseModel):
    """Point-in-time immutable snapshot view."""

    key: str
    revision: int
    content: str
    tags: dict[str, str] = Field(default_factory=dict)
    is_tombstone: bool = False
    created_at: float
    checksum_crc32: int = 0


class RollbackRequestDTO(BaseModel):
    """Request to safely rollback a key to a prior historical revision."""

    key: str = Field(min_length=1, description="Target key to revert")
    target_revision: int = Field(ge=1, description="Historical revision number to restore")


class RetractRequestDTO(BaseModel):
    """Request to publish a tombstone retraction revision."""

    key: str = Field(min_length=1, description="Target key to retract")


class DurableRevisionStatsDTO(BaseModel):
    """Aggregated operational telemetry statistics."""

    total_receipts: int
    applied_receipts: int
    contention_receipts: int
    validation_failed_receipts: int
    quarantined_receipts: int
    superseded_receipts: int
    reverted_receipts: int
    failed_durable_receipts: int
    active_locks: int
    total_snapshots: int
