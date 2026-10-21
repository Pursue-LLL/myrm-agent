"""
[POS] app/schemas/memory_migration.py
[INPUT] pydantic
[OUTPUT] CompetitorDetectResponseDTO, CompetitorIngestRequestDTO, CompetitorIngestResponseDTO

Pydantic DTOs for third-party competitor asset detection and ingestion.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
