"""Data schemas for the Wiki task usage ledger and layer document listing.

[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- UsageLedgerItem, UsageLedgerRecord, WikiLayerItem

[POS]
Domain schemas for task delivery usage auditing and per-layer document summaries.
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


class WikiLayerItem(BaseModel):
    """Summary of a single markdown or structured document within a wiki layer."""

    slug: str = Field(..., description="Document slug or filename")
    title: str = Field(..., description="Document title")
    relative_path: str = Field(..., description="Relative path within wiki vault")
    publish_status: str = Field("published", description="draft or published")
    updated_at: str = Field("", description="Last modified ISO timestamp")
    content_snippet: str = Field("", description="First few lines of document body")
    source_task_id: str | None = Field(None, description="Source task ID if written back from a task")
    file_type: str = Field("markdown", description="File type: markdown or json")

