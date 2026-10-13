"""Schema definitions for dynamic user preference fitting and pulse radar inspector.

[INPUT]
- Pydantic BaseModel, Field

[OUTPUT]
- PreferenceRadarStateResponse: DTO representing the 5-dimensional preference weights
- UpdatePreferenceRadarRequest: Manual fine-tuning or locking request

[POS]
Data contracts for session-level dynamic preference radar endpoints and inspector drawers.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PreferenceRadarStateResponse(BaseModel):
    """Multi-dimensional user preference radar state."""

    session_id: str = Field(..., description="Target session or conversation ID")
    recency: float = Field(..., ge=0.05, le=3.0, description="Preference weight for recency & temporal pulse")
    actionability: float = Field(..., ge=0.05, le=3.0, description="Preference weight for code & actionable steps")
    technical_depth: float = Field(..., ge=0.05, le=3.0, description="Preference weight for architectural & technical depth")
    conciseness: float = Field(..., ge=0.05, le=3.0, description="Preference weight for brevity and precision")
    breadth: float = Field(..., ge=0.05, le=3.0, description="Preference weight for high-level panoramic coverage")
    locked: bool = Field(False, description="Whether automated online fitting is locked by user")
    last_updated: datetime = Field(..., description="Last update timestamp in UTC")
    effective_signal_weights: dict[str, float] = Field(
        default_factory=dict, description="Calculated weights mapped to memory retriever signals"
    )


class UpdatePreferenceRadarRequest(BaseModel):
    """Request to manually tune or lock radar dimensions."""

    recency: float | None = Field(None, ge=0.05, le=3.0)
    actionability: float | None = Field(None, ge=0.05, le=3.0)
    technical_depth: float | None = Field(None, ge=0.05, le=3.0)
    conciseness: float | None = Field(None, ge=0.05, le=3.0)
    breadth: float | None = Field(None, ge=0.05, le=3.0)
    locked: bool | None = Field(None, description="Toggle auto-fitting lock")
    reset_to_neutral: bool = Field(False, description="Reset all dimensions back to neutral prior 1.0")
