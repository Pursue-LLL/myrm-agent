"""Data contracts, models, and callbacks for cross-session memory consolidation.

[INPUT]
- memory.types::{AnyMemory, ConflictResolution, MemoryStatus, MemoryType} (POS: memory records, conflict enum, lifecycle status and memory types)

[OUTPUT]
- ConsolidationAction, MergeOp, CorrectOp, UpdateContentOp, ConsolidationOp
- ConsolidationBatch: the memories of one namespace group with the operations and insights proposed for them
- ConsolidationStats: one cycle's counters and the insights the store took; ConsolidationResponse: the model's parsed answer
- PreImage, UndoJournal: what a cycle changed, recorded as it happened
- ConflictContext, ConflictCallback, ConsolidationCompleteCallback
- CONSOLIDATION_INSIGHT_TAG, CONSOLIDATION_SOURCE_KEY, CONSOLIDATED_FLAG_KEY, is_folded_fragment: markers of consolidation's own output

[POS]
Domain models, DTOs, and protocol callback types for cross-session memory consolidation, plus the markers that
identify what consolidation itself wrote (its insights and its merged memories) and the fragments a merge folded away.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from myrm_agent_harness.toolkits.memory.types import MemoryStatus

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import (
        AnyMemory,
        ConflictResolution,
        MemoryType,
    )

_PROFILE_KEY_LAST_CONSOLIDATED = "_system.last_consolidated_at"

# Markers on what consolidation writes: a semantic insight, and the metadata key of a merged semantic memory.
# Writers stamp them and readers (pattern discovery, the candidate window) recognize them through these names.
CONSOLIDATION_INSIGHT_TAG = "consolidation-insight"
CONSOLIDATION_SOURCE_KEY = "consolidation_source"
# Set on a source a merge folded into its product: the fragment stays stored (and undoable) but is no longer analyzed.
CONSOLIDATED_FLAG_KEY = "consolidated"


def is_folded_fragment(memory: AnyMemory) -> bool:
    """Whether a merge already folded this memory into its product, so only the product carries its content on."""
    return memory.metadata.get(CONSOLIDATED_FLAG_KEY) is True


@dataclass(frozen=True, slots=True)
class ConflictContext:
    """Context passed to the conflict callback when a high-importance correction is uncertain."""

    old_memory_id: str
    old_content: str
    new_content: str
    accuracy_score: float
    importance: float
    merge_suggestion: str
    memory_type: MemoryType


ConflictCallback = Callable[[ConflictContext], Awaitable["ConflictResolution"]]
ConsolidationCompleteCallback = Callable[["ConsolidationStats"], Awaitable[None]]


class ConsolidationAction(StrEnum):
    MERGE = "merge"
    CORRECT = "correct"
    UPDATE_CONTENT = "update_content"


class MergeOp(BaseModel):
    action: str = ConsolidationAction.MERGE
    source_ids: list[str]
    merged_content: str
    importance: float = Field(default=0.7, ge=0.0, le=1.0)
    accuracy_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Score (0-1): Does the merged memory accurately reflect the underlying truth without hallucination?",
    )
    anti_fragmentation_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Score (0-1): Does this operation combine fragmented pieces into a cohesive whole?",
    )
    redundancy_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Score (0-1): Does this operation successfully eliminate duplicate or overlapping information?",
    )
    reasoning: str = Field(default="", description="Reasoning for the scores.")


class CorrectOp(BaseModel):
    action: str = ConsolidationAction.CORRECT
    memory_id: str
    corrected_content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    accuracy_score: float = Field(default=1.0, ge=0.0, le=1.0)
    anti_fragmentation_score: float = Field(default=1.0, ge=0.0, le=1.0)
    redundancy_score: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str = Field(default="")


class UpdateContentOp(BaseModel):
    action: str = ConsolidationAction.UPDATE_CONTENT
    memory_id: str
    new_content: str
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    accuracy_score: float = Field(default=1.0, ge=0.0, le=1.0)
    anti_fragmentation_score: float = Field(default=1.0, ge=0.0, le=1.0)
    redundancy_score: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str = Field(default="")


ConsolidationOp = MergeOp | CorrectOp | UpdateContentOp


@dataclass(frozen=True, slots=True)
class ConsolidationBatch:
    """The memories of one namespace group and what the model proposed for them.

    ``operations`` name full memory ids and passed every check that needs no store access; ``memories`` are the
    texts the model read, which the apply step compares with what the store holds by then. ``guard_patched`` and
    ``rejected`` count the proposals the entity guard repaired and the checks turned away.
    """

    memories: Sequence[AnyMemory]
    operations: list[ConsolidationOp] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    guard_patched: int = 0
    rejected: int = 0


class PreImage(BaseModel):
    """A memory's restorable fields as they were before a cycle first wrote to it.

    No text is kept: a rewritten memory holds its previous content in its own metadata, so the journal stays numbers
    and names only.
    """

    importance: float | None
    confidence: float | None
    status: MemoryStatus
    metadata_keys: list[str]
    content_edited: bool = False


class UndoJournal(BaseModel):
    """What a cycle changed, recorded as it happened, so undoing it restores state instead of reconstructing it."""

    created: list[str] = Field(default_factory=list)
    touched: dict[str, PreImage] = Field(default_factory=dict)

    @property
    def change_count(self) -> int:
        return len(self.created) + len(self.touched)


class ConsolidationStats(BaseModel):
    merged: int = 0
    corrected: int = 0
    updated: int = 0
    errors: int = 0
    routed_to_user: int = 0
    guard_patched: int = 0
    rejected: int = 0
    total_processed: int = 0
    duration_ms: float = 0.0
    input_count: int = 0
    enriched_count: int = 0
    insights: tuple[str, ...] = ()  # what the store took, not every insight the model proposed
    undo: UndoJournal = Field(default_factory=UndoJournal)
    aborted: bool = False


class ConsolidationResponse(BaseModel):
    """Parsed LLM consolidation response containing operations and insights."""

    operations: list[ConsolidationOp] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)


__all__ = [
    "CONSOLIDATED_FLAG_KEY",
    "CONSOLIDATION_INSIGHT_TAG",
    "CONSOLIDATION_SOURCE_KEY",
    "ConflictCallback",
    "ConflictContext",
    "ConsolidationAction",
    "ConsolidationBatch",
    "ConsolidationCompleteCallback",
    "ConsolidationOp",
    "ConsolidationResponse",
    "ConsolidationStats",
    "CorrectOp",
    "MergeOp",
    "PreImage",
    "UndoJournal",
    "UpdateContentOp",
    "_PROFILE_KEY_LAST_CONSOLIDATED",
    "is_folded_fragment",
]
