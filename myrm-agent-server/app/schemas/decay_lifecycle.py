"""Pydantic schemas for Ebbinghaus decay and tiered storage lifecycle.

[INPUT]
- Raw request payloads for lifecycle evaluation and revival.

[OUTPUT]
- Pydantic response models validating lifecycle migrations and cold archives.

[POS]
- app.schemas.decay_lifecycle
"""

from pydantic import BaseModel, ConfigDict, Field


class EvaluateLifecycleRequest(BaseModel):
    """Request to trigger periodic decay re-evaluation and tier transitions."""

    model_config = ConfigDict(extra="forbid")

    current_time: float | None = Field(
        default=None, description="Optional simulated evaluation epoch timestamp"
    )


class EvaluateLifecycleResponse(BaseModel):
    """Report detailing tier distributions and migrated memory IDs."""

    total_evaluated: int = Field(description="Total memories evaluated")
    hot_count: int = Field(description="Active HOT memory count")
    warm_count: int = Field(description="Intermediate WARM memory count")
    cold_count: int = Field(description="Archived COLD memory count")
    migrated_count: int = Field(description="Number of memories that changed tier")
    migrated_memory_ids: list[str] = Field(
        default_factory=list, description="IDs of transitioned memories"
    )


class ReviveMemoryRequest(BaseModel):
    """Payload to reactivate an archived memory back into the HOT tier."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(description="Memory identifier to revive")
    boost_importance: float | None = Field(
        default=None, ge=0.1, le=1.0, description="Optional new boosted importance weight"
    )


class ReviveMemoryResponse(BaseModel):
    """Confirmation of memory revival."""

    memory_id: str = Field(description="Revived memory identifier")
    new_score: float = Field(description="Refreshed decay retention score")
    new_tier: str = Field(description="Current tier post-revival (HOT)")
    access_count: int = Field(description="Updated access frequency count")


class ColdArchiveItemSchema(BaseModel):
    """Serialized cold archive memory record."""

    memory_id: str = Field(description="Memory ID")
    content: str = Field(description="Archived text")
    importance: float = Field(description="Importance")
    created_at: float = Field(description="Creation epoch timestamp")
    last_accessed_at: float = Field(description="Last accessed epoch timestamp")
    access_count: int = Field(description="Access count")
    pinned: bool = Field(description="Pinned status")
    score: float = Field(description="Final decay score")
    tier: str = Field(description="Storage tier (COLD)")


class ExportColdArchiveResponse(BaseModel):
    """Export container for cold archived memories."""

    total_archived: int = Field(description="Number of exported cold records")
    records: list[ColdArchiveItemSchema] = Field(
        default_factory=list, description="Exported records"
    )
