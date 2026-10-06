"""
[POS] app/schemas/memory_drift.py
[INPUT] pydantic
[OUTPUT] DriftCheckRequestDTO, MemoryDriftFindingDTO, DriftCheckResponseDTO, BatchDriftCheckRequestDTO, BatchDriftCheckResponseDTO

Pydantic DTOs for ground truth priority and memory drift stale defense.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MemoryDriftFindingDTO(BaseModel):
    """Information regarding a detected discrepancy between memory and ground truth."""

    model_config = ConfigDict(extra="forbid")

    drift_type: str = Field(..., description="Classification of drift detected")
    reference_target: str = Field(..., description="Target file path, config key, or symbol name")
    detail: str = Field(..., description="Explanation of the discrepancy")
    is_stale: bool = Field(default=True, description="Whether this finding warrants stale deprecation")


class DriftCheckRequestDTO(BaseModel):
    """Payload to evaluate an individual memory candidate for physical world drift."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., description="Unique memory identifier")
    content: str = Field(..., min_length=1, description="Memory text content to inspect")
    workspace_root: str | None = Field(default=None, description="Optional workspace root directory path")
    recorded_path: str | None = Field(default=None, description="Explicit file path bound to memory if any")
    recorded_symbol: str | None = Field(default=None, description="Explicit symbol bound to memory if any")


class DriftCheckResponseDTO(BaseModel):
    """Result of ground truth drift evaluation."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., description="Evaluated memory identifier")
    is_drifted: bool = Field(..., description="True if any drift discrepancy was confirmed")
    confidence_penalty: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence deduction applied (0.0 means pristine, 0.6+ means stale)",
    )
    findings: list[MemoryDriftFindingDTO] = Field(
        default_factory=list,
        description="List of detected drift findings",
    )
    decorated_content: str = Field(
        ...,
        description="Memory text with stale warning prefix injected if drifted",
    )


class BatchDriftCheckRequestDTO(BaseModel):
    """Batch evaluation payload for candidate memories."""

    model_config = ConfigDict(extra="forbid")

    items: list[DriftCheckRequestDTO] = Field(..., min_length=1, description="List of memory items to check")
    workspace_root: str | None = Field(default=None, description="Global fallback workspace root path")


class BatchDriftCheckResponseDTO(BaseModel):
    """Summary of batch drift evaluation."""

    model_config = ConfigDict(extra="forbid")

    results: list[DriftCheckResponseDTO] = Field(default_factory=list, description="Per-memory drift evaluation outcomes")
    total_checked: int = Field(ge=0, description="Total number of memories evaluated")
    drifted_count: int = Field(ge=0, description="Count of memories where drift was confirmed")
