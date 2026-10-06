"""
[POS] app/schemas/memory_openclaw.py
[INPUT] pydantic
[OUTPUT] OpenClawRescueReportDTO, OpenClawSessionNodeDTO, OpenClawMemoryEntryDTO, OpenClawRescuePreviewRequestDTO, OpenClawRescuePreviewResponseDTO, OpenClawImportV2RequestDTO, OpenClawImportV2ResponseDTO

Pydantic DTOs for OpenClaw 2.0 format adapter, Swarm topology, and crash recovery rescue pipeline.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OpenClawRescueReportDTO(BaseModel):
    """Diagnostics and telemetry generated during crash recovery extraction."""

    model_config = ConfigDict(extra="forbid")

    db_path: str = Field(..., description="Target SQLite database path")
    is_sqlite_corrupt: bool = Field(..., description="Whether corruption was detected")
    integrity_check_output: str = Field(..., description="Output from PRAGMA integrity_check")
    total_rows_scanned: int = Field(..., ge=0, description="Total rows inspected")
    recovered_count: int = Field(..., ge=0, description="Total intact rows extracted")
    corrupted_rows_skipped: int = Field(..., ge=0, description="Corrupted rows safely skipped")
    rescue_success_rate: float = Field(..., ge=0.0, le=1.0, description="Ratio of recovered rows")


class OpenClawSessionNodeDTO(BaseModel):
    """Extracted session node preserving parent-child Swarm topology."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Session identifier")
    title: str = Field(..., description="Session title or summary")
    parent_session_id: str | None = Field(default=None, description="Parent session ID in Swarm tree")
    swarm_agent_id: str | None = Field(default=None, description="Assigned swarm worker agent ID")
    owner_id: str = Field(default="default_user", description="Owner user ID")
    created_at: str = Field(default="", description="ISO timestamp")


class OpenClawMemoryEntryDTO(BaseModel):
    """Extracted memory entry supporting private or shared scope."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(..., description="Memory record identifier")
    content: str = Field(..., description="Memory content text")
    category: str = Field(default="general", description="Memory categorization")
    scope: str = Field(default="shared", description="Scope: private or shared")
    target_agent_id: str | None = Field(default=None, description="Target private agent ID if private")
    importance: float = Field(default=0.7, ge=0.0, le=1.0, description="Memory importance score")
    created_at: str = Field(default="", description="ISO timestamp")


class OpenClawRescuePreviewRequestDTO(BaseModel):
    """Payload to trigger diagnosis and rescue preview of an OpenClaw SQLite file."""

    model_config = ConfigDict(extra="forbid")

    db_path: str = Field(..., description="Path to OpenClaw SQLite database file")


class OpenClawRescuePreviewResponseDTO(BaseModel):
    """Diagnosis report and preview of salvageable records."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether inspection succeeded")
    report: OpenClawRescueReportDTO = Field(..., description="Crash recovery diagnostic report")
    sessions_preview: list[OpenClawSessionNodeDTO] = Field(..., description="Preview of rescued sessions")
    memories_preview: list[OpenClawMemoryEntryDTO] = Field(..., description="Preview of rescued memories")
    warnings: list[str] = Field(default_factory=list, description="Diagnostic warnings")


class OpenClawImportV2RequestDTO(BaseModel):
    """Payload to import OpenClaw 2.0 data either from SQLite file or dictionary payload."""

    model_config = ConfigDict(extra="forbid")

    db_path: str | None = Field(default=None, description="Optional path to SQLite file")
    raw_sessions: list[dict[str, object]] | None = Field(default=None, description="Optional raw session dicts")
    raw_memories: list[dict[str, object]] | None = Field(default=None, description="Optional raw memory dicts")
    default_scope_mode: str = Field(
        default="preserve",
        description="Scope handling: preserve, force_private, force_shared",
    )


class OpenClawImportV2ResponseDTO(BaseModel):
    """Result summary of OpenClaw 2.0 import and ingestion into Myrm memory."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether import completed successfully")
    imported_sessions_count: int = Field(..., ge=0, description="Number of sessions ingested")
    imported_memories_count: int = Field(..., ge=0, description="Number of memories ingested")
    rescue_report: OpenClawRescueReportDTO | None = Field(default=None, description="Rescue report if from SQLite")
    message: str = Field(..., description="Summary message")
    warnings: list[str] = Field(default_factory=list, description="Import warnings")
