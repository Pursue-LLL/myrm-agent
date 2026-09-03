"""System API Pydantic Request & Response Schemas.

[INPUT]
- app.services.system.storage_service::DatabaseStorageBreakdown, SubdirUsage (POS: Storage Breakdown Models)

[OUTPUT]
- IngressRequirementResponse
- StorageInfoResponse
- StorageOptimizePreflightResponse
- StorageOptimizeRequest
- StorageOptimizeResponse
- SandboxRecreateResponse
- StorageCategoryItem
- StateSnapshotItem
- StorageGovernanceReportResponse
- StorageCompactionRequest
- StorageCompactionResponse
- CreateSnapshotRequest
- SnapshotActionResponse

[POS]
Pydantic schemas and serialization models for the System API endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel
from app.services.system.storage_service import DatabaseStorageBreakdown, SubdirUsage


class IngressRequirementResponse(BaseModel):
    required: bool
    has_public_ingress: bool
    reasons: list[str]
    channels: dict[str, str]


class StorageInfoResponse(BaseModel):
    data_dir: str
    disk_total_bytes: int
    disk_used_bytes: int
    disk_free_bytes: int
    subdirs: list[SubdirUsage]
    db_breakdown: DatabaseStorageBreakdown | None = None


class StorageOptimizePreflightResponse(BaseModel):
    data_dir: str
    db_breakdown: DatabaseStorageBreakdown
    disk_free_bytes: int
    can_deep_optimize: bool
    recommended_mode: str
    active_background_jobs: int
    is_safe_to_optimize: bool
    reason: str | None = None


class StorageOptimizeRequest(BaseModel):
    mode: str = "deep"  # "deep" | "light"
    create_backup: bool = True


class StorageOptimizeResponse(BaseModel):
    status: str
    mode: str
    before_bytes: int
    after_bytes: int
    reclaimed_bytes: int
    reclaimed_percentage: float
    backup_path: str | None = None
    duration_ms: int
    message: str


class SandboxRecreateResponse(BaseModel):
    status: str
    message: str


class StorageCategoryItem(BaseModel):
    category: str
    display_name: str
    bytes: int
    item_count: int
    percentage: float
    details: dict[str, int] = {}


class StateSnapshotItem(BaseModel):
    snapshot_id: str
    label: str
    size_bytes: int
    created_at: str
    checksum: str
    file_count: int


class StorageGovernanceReportResponse(BaseModel):
    total_storage_bytes: int
    disk_total_bytes: int
    disk_free_bytes: int
    disk_used_percentage: float
    categories: list[StorageCategoryItem]
    snapshots: list[StateSnapshotItem]
    recommended_actions: list[str]
    is_growth_healthy: bool
    generated_at: str


class StorageCompactionRequest(BaseModel):
    purge_orphan_checkpoints: bool = True
    incremental_pages: int = 500


class StorageCompactionResponse(BaseModel):
    success: bool
    initial_bytes: int
    final_bytes: int
    freed_bytes: int
    purged_checkpoints: int
    wal_truncated: bool
    duration_ms: float
    message: str


class CreateSnapshotRequest(BaseModel):
    label: str


class SnapshotActionResponse(BaseModel):
    success: bool
    message: str
    snapshot: StateSnapshotItem | None = None
