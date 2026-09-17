"""Domain Mesh schemas for three-domain L0/L1/L2 progressive memory API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProgressiveHighlight(BaseModel):
    id: str
    l0: str
    l1: str
    category: str
    memory_type: str
    updated_at: str


class DomainBucketOverview(BaseModel):
    domain: str
    total_count: int
    category_counts: dict[str, int] = Field(default_factory=dict)
    highlights: list[ProgressiveHighlight] = Field(default_factory=list)


class DomainMeshOverviewResponse(BaseModel):
    user: DomainBucketOverview
    assistant: DomainBucketOverview
    task: DomainBucketOverview
    total_memories: int


class DrillDownResponse(BaseModel):
    id: str
    domain: str
    category: str
    memory_type: str
    l0: str
    l1: str
    l2_content: str
    created_at: str
    updated_at: str
    metadata: dict[str, object] = Field(default_factory=dict)


class HermesMigrationRequest(BaseModel):
    content: str
    format: str = "markdown"


class HermesMigrationResponse(BaseModel):
    success_count: int
    fail_count: int
    message: str
