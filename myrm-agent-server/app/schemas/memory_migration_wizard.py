"""Data transfer objects for multi-platform memory migration wizard API.

[POS]
Pydantic contracts for scanning external competitor memory assets, initiating
deduplicated import pipelines, chunking telemetry, and migration auditing.

[INPUT]
- typing.Literal, pydantic.BaseModel, pydantic.Field

[OUTPUT]
- MigrationSourceTypeDTO, DetectedCandidateDTO, MigrationDetectRequestDTO
- MigrationDetectResponseDTO, MigrationImportRequestDTO, MigrationRunReportDTO
- MigrationImportResponseDTO, MigrationSourcesListResponseDTO
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MigrationSourceTypeDTO = Literal[
    "openclaw",
    "hermes",
    "chatgpt_export",
    "claude_project",
    "markdown_tree",
    "generic_json",
]


class DetectedCandidateDTO(BaseModel):
    """Metadata describing a detected external competitor memory file or directory."""

    source_type: MigrationSourceTypeDTO = Field(description="Identified ecosystem origin")
    artifact_path: str = Field(description="Absolute local filesystem path to the asset")
    estimated_entries: int = Field(default=0, ge=0, description="Estimated count of memories/facts")
    summary: str = Field(description="Human-readable summary of detected contents")


class MigrationDetectRequestDTO(BaseModel):
    """Payload to scan local workspace or system directories for external memory assets."""

    custom_candidates: list[str] = Field(
        default_factory=list, description="Optional custom directory or file paths to inspect"
    )


class MigrationDetectResponseDTO(BaseModel):
    """Outcome of scanning local paths for competitor memory files."""

    total_detected: int = Field(ge=0, description="Count of distinct external artifacts found")
    candidates: list[DetectedCandidateDTO] = Field(description="List of detected memory assets")


class MigrationImportRequestDTO(BaseModel):
    """Payload requesting one-click memory asset parsing, chunking, and ingestion."""

    source_type: MigrationSourceTypeDTO = Field(description="Target ecosystem parser format")
    file_path: str | None = Field(default=None, description="Absolute local filesystem path to import")
    raw_content: str | None = Field(default=None, description="Optional in-memory raw payload text")
    source_label: str = Field(default="wizard_import", description="Human-readable audit label")


class MigrationRunReportDTO(BaseModel):
    """Audit report for an executed memory migration run."""

    migration_id: str = Field(description="Unique migration execution identifier")
    source_type: MigrationSourceTypeDTO = Field(description="Target platform migrated")
    source_path: str = Field(description="Origin filesystem path or memory label ingested")
    total_scanned: int = Field(ge=0, description="Total raw entries detected and scanned")
    total_admitted: int = Field(ge=0, description="Net new distinct entries admitted")
    total_skipped_duplicates: int = Field(
        ge=0, description="Redundant entries filtered by fingerprint deduplication"
    )
    total_chunks_generated: int = Field(
        ge=0, description="Total 400/80 sliding window semantic chunks created"
    )
    vector_ingestion_status: str = Field(description="Status of vector indexing")
    latency_ms: float = Field(ge=0.0, description="Execution duration in milliseconds")
    timestamp: float = Field(description="Epoch completion timestamp")


class MigrationImportResponseDTO(BaseModel):
    """Outcome of one-click migration execution."""

    success: bool = Field(description="Whether migration executed without critical errors")
    report: MigrationRunReportDTO = Field(description="Audit and telemetry report")


class MigrationSourcesListResponseDTO(BaseModel):
    """List of supported external memory formats and ecosystems."""

    supported_sources: list[MigrationSourceTypeDTO] = Field(
        description="Supported platform source identifiers"
    )
