"""
[POS] app/schemas/memory_migration.py
[INPUT] pydantic
[OUTPUT] ExportBundleRequestDTO, ExportBundleResponseDTO, RestoreBundleRequestDTO, RestoreBundleResponseDTO, CompetitorDetectResponseDTO, CompetitorIngestRequestDTO, CompetitorIngestResponseDTO

Pydantic DTOs for sovereign asset package migration and cross-machine restore protocol.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExportBundleRequestDTO(BaseModel):
    """Payload to trigger export of digital sovereign assets into a .myrmpkg bundle."""

    model_config = ConfigDict(extra="forbid")

    source_dir: str | None = Field(
        default=None,
        description="Optional custom root directory containing memory data. Defaults to active memory storage.",
    )
    output_bundle_path: str | None = Field(
        default=None,
        description="Optional target destination file path for .myrmpkg. Defaults to temp/export dir.",
    )
    include_categories: list[str] = Field(
        default_factory=lambda: [
            "wiki_memory",
            "sqlite_database",
            "handoff_record",
            "unload_snapshot",
            "agent_rule",
            "custom_skill",
        ],
        description="List of asset categories to encompass in export",
    )
    custom_description: str = Field(
        default="Myrm sovereign asset backup",
        description="User or automated description note",
    )


class ExportBundleResponseDTO(BaseModel):
    """Summary result returned after exporting sovereign bundle."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether bundle export succeeded")
    bundle_path: str = Field(..., description="Absolute path to generated .myrmpkg archive")
    package_id: str = Field(..., description="Unique package identifier")
    asset_count: int = Field(..., ge=0, description="Number of assets archived")
    total_bytes: int = Field(..., ge=0, description="Total uncompressed size in bytes")
    sha256: str = Field(..., description="SHA-256 integrity hash of bundle file")


class RestoreBundleRequestDTO(BaseModel):
    """Payload to unpack, verify, and restore a .myrmpkg bundle."""

    model_config = ConfigDict(extra="forbid")

    bundle_path: str = Field(..., min_length=1, description="Absolute path to .myrmpkg archive")
    target_destination_dir: str | None = Field(
        default=None,
        description="Optional destination directory. Defaults to active memory storage root.",
    )
    current_workspace_root: str | None = Field(
        default=None,
        description="Current workspace root path for dynamic path remapping. Defaults to cwd.",
    )
    overwrite_existing: bool = Field(default=False, description="Whether to overwrite existing files")


class RestoreBundleResponseDTO(BaseModel):
    """Summary result returned after restoring sovereign bundle."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether bundle restoration succeeded")
    package_id: str = Field(..., description="Package identifier restored")
    restored_assets: list[str] = Field(default_factory=list, description="Relative paths of restored assets")
    remapped_paths_count: int = Field(default=0, ge=0, description="Count of hardcoded path occurrences remapped")
    source_workspace_root: str = Field(..., description="Original workspace path from manifest")
    target_workspace_root: str = Field(..., description="Applied new active workspace root path")


class CompetitorDetectResponseDTO(BaseModel):
    """Information discovered regarding competitor assets on local host."""

    model_config = ConfigDict(extra="forbid")

    detected_competitors: list[str] = Field(
        default_factory=list, description="List of recognized competitor keys: hermes, claude_code, codex"
    )
    hermes_dir: str | None = Field(default=None, description="Discovered path to ~/.hermes directory")
    claude_code_rule_path: str | None = Field(default=None, description="Discovered path to CLAUDE.md")
    codex_rule_path: str | None = Field(default=None, description="Discovered path to AGENTS.md")


class CompetitorIngestRequestDTO(BaseModel):
    """Payload to translate and ingest third-party competitor data into Myrm."""

    model_config = ConfigDict(extra="forbid")

    competitor: str = Field(..., description="Competitor identifier: hermes, claude_code, or codex")
    source_path: str = Field(..., min_length=1, description="Path to competitor folder or rule file")
    target_destination_dir: str | None = Field(
        default=None,
        description="Destination directory in Myrm. Defaults to active memory storage.",
    )


class CompetitorIngestResponseDTO(BaseModel):
    """Result report following ingestion from competitor."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether ingestion concluded without error")
    imported_rules_count: int = Field(default=0, ge=0, description="Count of rules converted")
    imported_skills_count: int = Field(default=0, ge=0, description="Count of skills imported")
    imported_memories_count: int = Field(default=0, ge=0, description="Count of memory markdown pages imported")
    details: list[str] = Field(default_factory=list, description="Detailed ingestion notices")
