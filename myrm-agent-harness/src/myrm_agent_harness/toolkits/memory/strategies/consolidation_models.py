"""Data contracts, models, and callbacks for cross-session memory consolidation.

[INPUT]
- memory.types::{ConflictResolution, MemoryStatus, MemoryType} (POS: conflict enum, lifecycle status and memory types)

[OUTPUT]
- ConsolidationAction, MergeOp, CorrectOp, UpdateContentOp, ConsolidationOp
- ConsolidationStats, ConsolidationResponse
- PreImage, UndoJournal: what a cycle changed, recorded as it happened
- ConflictContext, ConflictCallback, ConsolidationCompleteCallback
- CONSOLIDATION_INSIGHT_TAG, CONSOLIDATION_SOURCE_KEY: markers of consolidation's own output

[POS]
Domain models, DTOs, and protocol callback types for cross-session memory consolidation, plus the markers that
identify what consolidation itself wrote (its insights and its merged memories).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from myrm_agent_harness.toolkits.memory.types import MemoryStatus

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import (
        ConflictResolution,
        MemoryType,
    )

_PROFILE_KEY_LAST_CONSOLIDATED = "_system.last_consolidated_at"

# Markers on what consolidation writes: a semantic insight, and the metadata key of a merged semantic memory.
# Writers stamp them and readers (pattern discovery, the candidate window) recognize them through these names.
CONSOLIDATION_INSIGHT_TAG = "consolidation-insight"
CONSOLIDATION_SOURCE_KEY = "consolidation_source"


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
    total_processed: int = 0
    duration_ms: float = 0.0
    input_count: int = 0
    enriched_count: int = 0
    insights: tuple[str, ...] = ()
    undo: UndoJournal = Field(default_factory=UndoJournal)
    aborted: bool = False


class ConsolidationResponse(BaseModel):
    """Parsed LLM consolidation response containing operations and insights."""

    operations: list[ConsolidationOp] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)


__all__ = [
    "CONSOLIDATION_INSIGHT_TAG",
    "CONSOLIDATION_SOURCE_KEY",
    "ConflictCallback",
    "ConflictContext",
    "ConsolidationAction",
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
]
