"""System API Pydantic Request & Response Schemas.

[INPUT]
- app.services.system.storage_service::DatabaseStorageBreakdown (POS: Storage Breakdown Models)

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
- CreateSnapshotRequest
- SnapshotActionResponse
- TelemetryPostureResponse

[POS]
Pydantic schemas and serialization models for the System API endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.system.storage_service import DatabaseStorageBreakdown


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
    db_breakdown: DatabaseStorageBreakdown


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
    bytes: int
    item_count: int
    percentage: float


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
    generated_at: str


class CreateSnapshotRequest(BaseModel):
    label: str


class PreUpdateSnapshotRequest(BaseModel):
    from_version: str
    to_version: str
    keep_latest: int = 5


class SnapshotActionResponse(BaseModel):
    success: bool
    message: str
    snapshot: StateSnapshotItem | None = None


class TelemetryPostureResponse(BaseModel):
    status: str
    initialized: bool
    has_sdk: bool
    endpoint: str | None = None
    protocol: str
    headers_configured: bool
    local_trace_only: bool
    exporter_type: str = "none"
    degraded_reason: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    three_tier_semantics: bool = True
    prompt_cache_metering: bool = True
    error: str | None = None

