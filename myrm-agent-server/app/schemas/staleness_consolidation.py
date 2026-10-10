"""Pydantic schemas for Auto Memory Staleness Decay and Consolidation Audit Suite (Item 158).

[INPUT]
- Memory profile payloads, touch recall triggers, audit scan requests, consolidation and archive bodies.

[OUTPUT]
- MemoryItemProfileDTO, RepoAssertionCheckResultDTO, ConsolidationProposalDTO, and MemoryAuditReportDTO.

[POS]
- Server-side DTO contracts for Item 158 AutoMemoryStalenessDecayAndConsolidationAuditSuite.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

MemoryStatusDTO = Literal[
    "active",
    "stale",
    "invalidated",
    "consolidated",
    "archived",
]


class MemoryItemProfileDTO(BaseModel):
    """Profile representing a single autonomous memory record with staleness lifecycle metrics."""

    memory_id: str
    content: str
    category: str = "general"
    created_at: str = ""
    last_recalled_at: str = ""
    recalled_count: int = 0
    staleness_score: float = 0.0
    status: MemoryStatusDTO = "active"
    referenced_paths: list[str] = Field(default_factory=list)
    referenced_assertions: list[str] = Field(default_factory=list)
    invalidation_reason: str | None = None
    subsumed_by_id: str | None = None


class RegisterMemoryRequest(BaseModel):
    """Payload to register an autonomous memory profile."""

    memory_id: str
    content: str
    category: str = "general"
    created_at: str = ""
    referenced_paths: list[str] = Field(default_factory=list)
    referenced_assertions: list[str] = Field(default_factory=list)


class TouchRecallRequest(BaseModel):
    """Payload to touch a memory upon successful recall, resisting half-life staleness decay."""

    memory_id: str
    now_iso: str | None = None


class RepoAssertionCheckResultDTO(BaseModel):
    """Diagnostic check result of verifying code assertions against physical workspace state."""

    memory_id: str
    is_valid: bool
    missing_paths: list[str] = Field(default_factory=list)
    failed_assertions: list[str] = Field(default_factory=list)
    diagnostic: str = ""


class ConsolidationProposalDTO(BaseModel):
    """Synthesized consolidation proposal unifying multiple fragmented memory rules."""

    proposal_id: str
    source_memory_ids: list[str]
    category: str
    proposed_content: str
    rationale: str


class MemoryAuditReportDTO(BaseModel):
    """Comprehensive health check report across all active, stale, and invalidated memories."""

    total_items: int
    active_items: int
    stale_items: int
    invalidated_items: int
    consolidated_items: int
    archived_items: int
    average_staleness: float
    invalidated_results: list[RepoAssertionCheckResultDTO] = Field(default_factory=list)
    consolidation_proposals: list[ConsolidationProposalDTO] = Field(default_factory=list)
    generated_at: str = ""


class RunAuditRequest(BaseModel):
    """Payload to trigger an on-demand memory audit scan."""

    workspace_dir: str | None = None
    now_iso: str | None = None


class ApplyConsolidationRequest(BaseModel):
    """Payload to approve and execute a consolidation proposal."""

    proposal_id: str
    now_iso: str | None = None


class ArchiveMemoriesRequest(BaseModel):
    """Payload to safely move stale or invalidated memories into archived state."""

    memory_ids: list[str]
