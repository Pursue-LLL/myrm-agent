"""[INPUT]
- enums::MemoryType / PendingResolutionAction (POS: 记忆枚举)
- records::ClaimMemory / ConversationMemory / EpisodicMemory / IntegrationMemory / ProceduralMemory / SemanticMemory / TaskDigestMemory (POS: 具体记忆模型)
- pydantic::BaseModel / Field (POS: 校验与序列化)

[OUTPUT]
- HitSource / RecallDebugTrace / MemorySearchResult / PendingRecord

[POS]
`memory/types_pkg/` 的检索结果与待审候选模型。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from myrm_agent_harness.toolkits.memory.score_honesty.models import ScoreBreakdown

from .enums import MemoryType, PendingResolutionAction
from .records import (
    ClaimMemory,
    ConversationMemory,
    EpisodicMemory,
    IntegrationMemory,
    ProceduralMemory,
    SemanticMemory,
    TaskDigestMemory,
)


class HitSource(BaseModel):
    """Source stream attribution and original rank for multi-source recall."""

    source: str = Field(..., description="Name of the retrieval stream/source (e.g. 'vector', 'fts', 'graph')")
    rank: int = Field(..., ge=0, description="0-indexed rank within that source stream")
    score: float = Field(default=0.0, description="Original source-specific raw score if available")

class RecallDebugTrace(BaseModel):
    """White-box audit trail for multi-source RRF ranking decisions."""

    hit_sources: list[HitSource] = Field(default_factory=list, description="All sources that retrieved this candidate")
    hit_count: int = Field(default=0, ge=0, description="Total number of distinct streams that hit this candidate")
    fused_score: float = Field(default=0.0, description="Composite score before normalization")
    raw_score: float | None = Field(default=None, description="Underlying raw retrieval score")
    tie_break_rank: int = Field(
        default=0, ge=0, description="Rank resolved after deterministic three-tier tie-breaking"
    )

class MemorySearchResult(BaseModel):
    """Search result with dual-track score honesty (raw similarity vs ranking score).

    ``score`` is aligned with ``ranking_score`` for compatibility.
    ``raw_score`` (and its alias ``raw_similarity``) retains the underlying physical
    retrieval relevance (e.g. cosine similarity or BM25) before pipeline reranking.
    ``ranking_score`` reflects the multi-stage pipeline ranking outcome.
    """

    memory: (
        SemanticMemory
        | EpisodicMemory
        | ConversationMemory
        | ProceduralMemory
        | ClaimMemory
        | IntegrationMemory
        | TaskDigestMemory
    )
    score: float = Field(default=0.0, description="Normalized relevance score in [0, 1]")
    raw_score: float | None = Field(
        default=None, description="Physical cosine/BM25 similarity before multi-stage reranking"
    )
    raw_similarity: float | None = Field(
        default=None, description="Physical cosine/BM25 similarity before multi-stage reranking (alias)"
    )
    ranking_score: float | None = Field(default=None, description="Composite ranking score after multi-stage pipeline")
    score_breakdown: ScoreBreakdown | None = Field(
        default=None, description="Detailed white-box attribution trace for composite score"
    )
    memory_type: MemoryType
    recall_debug: RecallDebugTrace | None = Field(
        default=None, description="Detailed white-box attribution trace for multi-source retrieval"
    )

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v: object) -> float:
        try:
            value = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        if value != value:  # NaN
            return 0.0
        return min(1.0, max(0.0, value))

    @field_validator("raw_score", "raw_similarity", "ranking_score", mode="before")
    @classmethod
    def _clamp_optional_score(cls, v: object) -> float | None:
        if v is None:
            return None
        try:
            value = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if value != value:  # NaN
            return 0.0
        return min(1.0, max(0.0, value))

    @model_validator(mode="before")
    @classmethod
    def _sync_dual_track_scores(cls, data: object) -> object:
        if isinstance(data, dict):
            # Sync raw_score and raw_similarity
            raw = data.get("raw_score")
            raw_sim = data.get("raw_similarity")
            if raw is None and raw_sim is not None:
                data["raw_score"] = raw_sim
            elif raw is not None and raw_sim is None:
                data["raw_similarity"] = raw
            elif raw is None and raw_sim is None and "score" in data:
                # Default raw_score to initial input score if not explicitly set
                data["raw_score"] = data["score"]
                data["raw_similarity"] = data["score"]

            # Sync score and ranking_score
            if data.get("ranking_score") is None and "score" in data:
                data["ranking_score"] = data["score"]
        return data

    @property
    def id(self) -> str:
        return self.memory.id

    @property
    def content(self) -> str:
        return self.memory.content

    @property
    def trace_id(self) -> str | None:
        """Execution trace ID associated with this memory."""
        return getattr(self.memory, "trace_id", None)

class PendingRecord(BaseModel):
    """A memory awaiting user approval or conflict resolution.

    Stores the original memory object as JSON so it can be fully
    reconstructed on approval without information loss.
    When ``is_conflict`` is True, the record represents a detected memory
    contradiction that requires user arbitration before automatic merging.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    memory_type: MemoryType
    content: str
    memory_data: dict[str, object] = Field(
        default_factory=dict, description="Serialised AnyMemory fields for lossless reconstruction"
    )
    source_chat_id: str | None = None
    source_message_id: str | None = None
    status: Literal["pending", "approved", "rejected", "resolved"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    is_conflict: bool = False
    conflict_old_memory_id: str | None = None
    conflict_old_content: str | None = None
    conflict_accuracy_score: float | None = None
    conflict_importance: float | None = None
    conflict_auto_resolve_at: datetime | None = None

    resolution_action: PendingResolutionAction = PendingResolutionAction.STORE
    target_memory_id: str | None = None
    target_content: str | None = Field(
        default=None,
        description="Content of the memory targeted by CORRECT/DELETE, captured for review display",
    )

    @property
    def confidence(self) -> float | None:
        """Confidence score of the candidate memory (0.0 to 1.0)."""
        raw = self.memory_data.get("confidence")
        if isinstance(raw, (int, float)):
            return float(raw)
        return None

    @property
    def importance(self) -> float | None:
        """Importance score of the candidate memory (0.0 to 1.0)."""
        if self.conflict_importance is not None:
            return self.conflict_importance
        raw = self.memory_data.get("importance")
        if isinstance(raw, (int, float)):
            return float(raw)
        return None

    @property
    def kind(self) -> str | None:
        """Projected category or kind of the candidate memory."""
        raw = self.memory_data.get("projected_category") or self.memory_data.get("kind")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None

    @property
    def influence_explanation(self) -> str | None:
        """Reasoning or explanation for why the candidate was extracted."""
        raw = self.memory_data.get("influence_explanation") or self.memory_data.get("reasoning")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None

    @property
    def expected_valid_days(self) -> int | None:
        """Estimated validity window in days."""
        raw = self.memory_data.get("expected_valid_days")
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
        return None

    @property
    def tags(self) -> list[str]:
        """Tags attached to the candidate memory."""
        raw = self.memory_data.get("tags")
        if isinstance(raw, list):
            return [str(item) for item in raw if isinstance(item, (str, int))]
        return []
