"""Data schemas for Wiki writeback, usage ledger, and review slip workflows.

[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- UsageLedgerItem, UsageLedgerRecord, ReviewSlipOption, ReviewSlipQuestion
- ReviewSlipBatch, WritebackApplyRequest, WritebackApplyResult

[POS]
Domain schemas for task delivery usage auditing, negative exclusion evaluation,
and single-click review slip decision capture.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UsageLedgerItem(BaseModel):
    """Single referenced or generated knowledge item in a task execution."""

    concept_or_path: str = Field(..., description="Concept path or document identifier")
    contribution_type: Literal["referenced", "derived", "modified", "omitted"] = Field(
        ..., description="How this item was utilized"
    )
    detail: str = Field("", description="Specific contribution summary or omission reason")


class UsageLedgerRecord(BaseModel):
    """Complete usage ledger for a completed delivery task."""

    task_id: str = Field(..., description="Unique task or session ID")
    title: str = Field(..., description="Task title")
    executed_at: str = Field(..., description="ISO 8601 execution timestamp")
    items: list[UsageLedgerItem] = Field(default_factory=list)
    deliverable_paths: list[str] = Field(default_factory=list)


class ReviewSlipOption(BaseModel):
    """Single selectable option in a review question."""

    id: str = Field(..., description="Option unique key, e.g., 'adopt_as_method'")
    label: str = Field(..., description="Human readable choice title")
    recommended: bool = Field(False, description="Whether this is the AI recommended path")
    target_layer: Literal["methods", "claims", "deliverables_only", "discard"] = Field(
        ..., description="Target destination if selected"
    )


class ReviewSlipQuestion(BaseModel):
    """Structured decision question generated at task completion."""

    question_id: str = Field(..., description="Question identifier")
    topic: str = Field(..., description="Candidate insight or methodology title")
    candidate_content: str = Field(..., description="Draft markdown snippet proposed for writeback")
    rationale: str = Field(..., description="Reasoning why this is worth retaining")
    options: list[ReviewSlipOption] = Field(default_factory=list)
    selected_option_id: str = Field("", description="User selected option ID")


class ReviewSlipBatch(BaseModel):
    """Batch of 1 to 5 synthesized decision questions for task author."""

    task_id: str
    title: str
    generated_at: str
    questions: list[ReviewSlipQuestion] = Field(default_factory=list)
    excluded_matches_count: int = Field(0, description="Number of items filtered by negative rules")


class WritebackDecisionItem(BaseModel):
    """User decision for a specific question."""

    question_id: str
    selected_option_id: str
    target_layer: Literal["methods", "claims", "deliverables_only", "discard"]
    candidate_title: str
    candidate_content: str
    source_deliverable: str = Field("", description="Source deliverable document relative path")


class WritebackApplyRequest(BaseModel):
    """Request to commit user decisions into the wiki."""

    task_id: str
    decisions: list[WritebackDecisionItem]
    source_deliverable: str = Field("", description="Default source deliverable document relative path")


class WritebackApplyResult(BaseModel):
    """Result of writeback execution."""

    task_id: str
    committed_count: int
    discarded_count: int
    created_paths: list[str] = Field(default_factory=list)
    message: str = "Writeback applied successfully"


class WikiLayerItem(BaseModel):
    """Summary of a single markdown document within a wiki layer."""

    slug: str = Field(..., description="Document slug or filename")
    title: str = Field(..., description="Document title")
    relative_path: str = Field(..., description="Relative path within wiki vault")
    publish_status: str = Field("published", description="draft or published")
    updated_at: str = Field("", description="Last modified ISO timestamp")
    content_snippet: str = Field("", description="First few lines of document body")
