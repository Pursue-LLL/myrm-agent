"""Pydantic schemas for Ebbinghaus decay and tiered storage lifecycle.

[INPUT]
- Raw request payloads for memory decay registration, evaluation, reranking, and revival.

[OUTPUT]
- Pydantic response models validating lifecycle migrations and fused rerank scores.

[POS]
- app.schemas.decay_lifecycle
"""

from pydantic import BaseModel, ConfigDict, Field


class RegisterMemoryDecayRequest(BaseModel):
    """Payload to register a memory entry into the decay lifecycle manager."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(description="Unique identifier of the memory item")
    content: str = Field(description="Memory content text")
    importance: float = Field(
        default=0.7, ge=0.1, le=1.0, description="Initial importance weight in [0.1, 1.0]"
    )
    pinned: bool = Field(default=False, description="Whether this memory is pinned (never decays)")
    created_at: float | None = Field(default=None, description="Optional creation epoch timestamp")


class RegisterMemoryDecayResponse(BaseModel):
    """Response confirming registration and initial tier placement."""

    memory_id: str = Field(description="Registered memory ID")
    initial_score: float = Field(description="Initial computed decay score")
    initial_tier: str = Field(description="Initial storage tier: HOT/WARM/COLD")
    pinned: bool = Field(description="Pin status")


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


class CandidateItemInput(BaseModel):
    """Raw candidate item for decay-aware retrieval reranking."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(description="Memory unique identifier")
    content: str = Field(description="Memory content")
    base_similarity: float = Field(
        ge=0.0, le=1.0, description="Vector cosine similarity score in [0.0, 1.0]"
    )


class RerankCandidatesRequest(BaseModel):
    """Request payload to fuse vector similarity with Ebbinghaus decay retention."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateItemInput] = Field(
        description="Candidate memories to score and sort"
    )
    decay_weight: float = Field(
        default=0.35, ge=0.0, le=1.0, description="Weight factor for decay score"
    )
    exclude_cold: bool = Field(
        default=True, description="Whether to filter out COLD archived memories"
    )
    current_time: float | None = Field(default=None, description="Optional timestamp")


class ScoredRerankItemSchema(BaseModel):
    """Scored memory candidate with combined similarity and decay weight."""

    memory_id: str = Field(description="Memory ID")
    content: str = Field(description="Memory text")
    base_similarity: float = Field(description="Original vector similarity")
    decay_score: float = Field(description="Calculated Ebbinghaus retention score")
    final_score: float = Field(description="Fused final ranking score")
    tier: str = Field(description="Storage tier (HOT, WARM, COLD)")


class RerankCandidatesResponse(BaseModel):
    """Ordered retrieval results post decay-aware reranking."""

    total_returned: int = Field(description="Number of candidates returned")
    items: list[ScoredRerankItemSchema] = Field(
        default_factory=list, description="Sorted ranked memory candidates"
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
