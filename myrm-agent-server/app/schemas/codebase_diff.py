"""Pydantic V2 schemas for codebase memory large diff fallback API endpoints.

[POS]
Data transfer objects and request/response models for codebase diff volume
evaluation, noise filtration, truncation detection, and topological summaries.

[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- DiffFileEntryDTO
- DirectoryAggregateDTO
- LargeDiffFallbackConfigDTO
- DiffFallbackVerdictDTO
- EvaluateDiffRequest
- EvaluateDiffResponse
- ParseNumstatRequest
- ParseNumstatResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiffFileEntryDTO(BaseModel):
    """File change entry data transfer object."""

    path: str = Field(description="Normalized relative path of the file")
    additions: int = Field(default=0, ge=0, description="Lines added")
    deletions: int = Field(default=0, ge=0, description="Lines deleted")
    category: str = Field(default="core_code", description="Classified syntactic category")
    is_generated: bool = Field(default=False, description="Whether marked as generated/vendor")
    is_renamed: bool = Field(default=False, description="Whether file was renamed or moved")
    old_path: str | None = Field(default=None, description="Previous path if renamed")
    patch_snippet: str | None = Field(default=None, description="Raw or truncated patch snippet")


class DirectoryAggregateDTO(BaseModel):
    """Aggregated diff metrics grouped by directory."""

    directory: str = Field(description="Directory or module tree name")
    file_count: int = Field(ge=0, description="Files changed in this directory")
    total_additions: int = Field(ge=0, description="Sum of additions")
    total_deletions: int = Field(ge=0, description="Sum of deletions")
    primary_category: str = Field(default="core_code", description="Dominant category in directory")


class LargeDiffFallbackConfigDTO(BaseModel):
    """Configuration thresholds for diff tier fallback."""

    micro_max_files: int = Field(default=20, ge=1)
    micro_max_lines: int = Field(default=800, ge=1)
    moderate_max_files: int = Field(default=100, ge=1)
    moderate_max_lines: int = Field(default=3000, ge=1)
    large_max_files: int = Field(default=500, ge=1)
    large_max_lines: int = Field(default=10000, ge=1)
    hard_file_cap: int = Field(default=3000, ge=10)
    filter_lockfiles_in_moderate: bool = Field(default=True)
    token_budget: int = Field(default=4000, ge=100)


class DiffFallbackVerdictDTO(BaseModel):
    """Synthesis result and diagnostics from diff fallback processing."""

    tier: str = Field(description="Selected execution tier: micro, moderate, large, massive")
    total_files: int = Field(ge=0, description="Total files supplied")
    total_additions: int = Field(ge=0, description="Total additions across all files")
    total_deletions: int = Field(ge=0, description="Total deletions across all files")
    is_truncated: bool = Field(default=False, description="Whether truncation was triggered")
    truncation_reason: str | None = Field(default=None, description="Reason if truncated")
    active_files_count: int = Field(ge=0, description="Files retained for fine indexing")
    filtered_noise_files_count: int = Field(ge=0, description="Count of bypassed/folded noise files")
    directory_aggregates: list[DirectoryAggregateDTO] = Field(default_factory=list)
    summary_text: str = Field(description="Safe context summary for memory ingestion")
    applied_optimizations: list[str] = Field(default_factory=list)


class EvaluateDiffRequest(BaseModel):
    """Request payload to evaluate diff entries and produce a verdict."""

    files: list[DiffFileEntryDTO] = Field(default_factory=list)
    declared_total_files: int | None = Field(
        default=None,
        description="Declared changed_files count from PR metadata to catch truncation",
    )
    is_api_truncated: bool = Field(default=False, description="Explicit API truncation flag")
    commit_message: str | None = Field(default=None, description="Optional commit message/intent")
    config: LargeDiffFallbackConfigDTO | None = Field(default=None)


class EvaluateDiffResponse(BaseModel):
    """Response containing the complete fallback verdict."""

    verdict: DiffFallbackVerdictDTO


class ParseNumstatRequest(BaseModel):
    """Request to parse git numstat plain text."""

    numstat_content: str = Field(description="Raw output from git diff --numstat")


class ParseNumstatResponse(BaseModel):
    """Parsed diff entries from git numstat."""

    entries: list[DiffFileEntryDTO] = Field(default_factory=list)
