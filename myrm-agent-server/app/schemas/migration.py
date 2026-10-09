"""[POS]: app/schemas/migration.py
[INPUT]: HTTP requests for detecting competitor memory assets and executing migrations.
[OUTPUT]: Pydantic schemas for detected artifacts, migration reports, and audit history.
"""

from pydantic import BaseModel, Field


class DetectedArtifactDTO(BaseModel):
    """DTO for detected competitor memory asset."""

    source_kind: str
    artifact_path: str
    estimated_entries: int
    detected_timestamp: float
    summary: str


class DetectArtifactsResponse(BaseModel):
    """Response containing list of detected local competitor memory artifacts."""

    total_detected: int
    artifacts: list[DetectedArtifactDTO]


class ImportArtifactRequest(BaseModel):
    """Request to import memory from an external local file path."""

    source_kind: str = Field(..., description="Ecosystem origin (hermes, openclaw, generic_json).")
    artifact_path: str = Field(..., min_length=1, description="Absolute filesystem path to file.")


class ImportRawTextRequest(BaseModel):
    """Request to import memory from an in-memory raw payload text."""

    source_kind: str = Field(..., description="Ecosystem origin (hermes, openclaw, generic_json).")
    raw_text: str = Field(..., min_length=1, description="Raw markdown or JSON payload.")
    source_label: str = Field(default="raw_buffer", description="Origin source tag or filename.")


class NormalizedMemoryDTO(BaseModel):
    """DTO for a normalized cognitive memory unit."""

    source_kind: str
    source_id: str
    raw_content: str
    normalized_content: str
    layer_recommendation: str
    tags: list[str] = Field(default_factory=list)
    content_hash: str
    provenance_meta: dict[str, str] = Field(default_factory=dict)


class MigrationReportResponse(BaseModel):
    """Audit report for executed competitor memory migration run."""

    migration_id: str
    source_kind: str
    source_path: str
    total_scanned: int
    total_imported: int
    total_skipped_duplicates: int
    imported_entries: list[NormalizedMemoryDTO] = Field(default_factory=list)
    timestamp: float


class MigrationHistoryResponse(BaseModel):
    """Listing of historical memory migration audits."""

    total_records: int
    history: list[MigrationReportResponse]
