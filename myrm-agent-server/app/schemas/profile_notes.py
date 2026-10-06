"""Pydantic schemas for DualLayerProfileMemoryBudgetAndGarbagePurgeGuard.

[INPUT]
- None (Self-contained Pydantic schema models)

[OUTPUT]
- ProfileNotesIntakeRequest, ProfileNotesIntakeResponse
- LayerWatermarkResponse, ProfileNotesStatusResponse
- ProfileNotesUpdateRequest, ProfileNotesContentResponse

[POS]
Data transfer schemas for User Profile and Working Notes memory layers,
intake noise filtering responses, and capacity watermark metrics.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProfileNotesIntakeRequest(BaseModel):
    """Request payload to test or filter incoming memory text."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, description="Candidate text to evaluate")
    layer_hint: str | None = Field(default=None, description="Optional manual layer hint ('user' or 'memory')")


class ProfileNotesIntakeResponse(BaseModel):
    """Response payload detailing intake filtering decision."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool = Field(..., description="Whether content is accepted into long-term memory")
    target_layer: str | None = Field(default=None, description="Target layer if accepted ('user' or 'memory')")
    rejected_reason: str | None = Field(default=None, description="Explanation if rejected as noise")
    garbage_category: str | None = Field(default=None, description="Noise category classification")


class LayerWatermarkResponse(BaseModel):
    """Capacity usage and watermark alert status for a single memory layer."""

    model_config = ConfigDict(extra="forbid")

    layer: str = Field(..., description="Layer name ('user' or 'memory')")
    current_chars: int = Field(..., ge=0, description="Current character count")
    max_chars: int = Field(..., gt=0, description="Max character budget")
    usage_ratio: float = Field(..., ge=0.0, description="Usage percentage ratio")
    level: str = Field(..., description="Watermark alert level ('safe', 'warning', 'critical', 'overflow')")
    warning_message: str | None = Field(default=None, description="Warning alert message if applicable")


class ProfileNotesStatusResponse(BaseModel):
    """Combined capacity watermark status for both memory layers."""

    model_config = ConfigDict(extra="forbid")

    user_watermark: LayerWatermarkResponse = Field(..., description="User profile watermark status")
    memory_watermark: LayerWatermarkResponse = Field(..., description="Agent working notes watermark status")


class ProfileNotesUpdateRequest(BaseModel):
    """Request payload to update content for either or both memory layers."""

    model_config = ConfigDict(extra="forbid")

    user_content: str | None = Field(default=None, description="Updated USER.md content")
    memory_content: str | None = Field(default=None, description="Updated MEMORY.md content")


class ProfileNotesContentResponse(BaseModel):
    """Current content and watermarks for both memory layers."""

    model_config = ConfigDict(extra="forbid")

    user_content: str = Field(..., description="Current USER.md content")
    memory_content: str = Field(..., description="Current MEMORY.md content")
    user_watermark: LayerWatermarkResponse = Field(..., description="User watermark status")
    memory_watermark: LayerWatermarkResponse = Field(..., description="Memory watermark status")
