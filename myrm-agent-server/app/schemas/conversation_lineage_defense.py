"""DTOs for conversation lineage deduplication and automation demotion.

[POS]
app/schemas/conversation_lineage_defense.py

[INPUT]
- pydantic BaseModel, Field, ConfigDict, typing literals

[OUTPUT]
- DTOs for conversation lineage deduplication and automation demotion
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConversationSourceKindDTO = Literal["interactive", "cron", "internal_worker"]
HydrationDetailLevelDTO = Literal["expanded_window", "compact_card"]


class CandidateSessionDTO(BaseModel):
    """Candidate session item for lineage defense evaluation."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    lineage_root_id: str
    parent_id: str | None = None
    generation: int = Field(default=1, ge=1)
    source_kind: ConversationSourceKindDTO = "interactive"
    title: str = ""
    raw_score: float = Field(default=0.0, ge=0.0)
    messages_context: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class HydratedHitDTO(BaseModel):
    """Hydrated session search hit with progressive window detail."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    lineage_root_id: str
    title: str
    source_kind: ConversationSourceKindDTO
    detail_level: HydrationDetailLevelDTO
    content_snippet: str
    window_messages: list[str] = Field(default_factory=list)
    token_estimate: int = Field(ge=0)
    is_demoted: bool
    is_lineage_primary: bool
    collapsed_generations_count: int = Field(ge=0)
    collapsed_session_ids: list[str] = Field(default_factory=list)


class LineageDedupAuditReportDTO(BaseModel):
    """Audit report DTO measuring recall blindness defense."""

    model_config = ConfigDict(extra="forbid")

    total_candidates: int
    retained_hits_count: int
    hidden_internal_count: int
    demoted_cron_count: int
    collapsed_lineage_count: int
    interactive_top1_ratio: float = Field(ge=0.0, le=1.0)
    estimated_tokens_saved: int
    token_saving_percent: float = Field(ge=0.0, le=100.0)


class LineageDefenseSearchRequestDTO(BaseModel):
    """Request payload for executing lineage defense search."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="", max_length=500)
    limit: int = Field(default=5, ge=1, le=20)
    include_internal: bool = Field(default=False)
    window_size: int = Field(default=5, ge=1, le=20)
    cron_weight_multiplier: float = Field(default=0.45, ge=0.05, le=1.0)
    candidates: list[CandidateSessionDTO] = Field(default_factory=list)


class LineageDefenseSearchResponseDTO(BaseModel):
    """Search response holding progressive hits and audit metrics."""

    model_config = ConfigDict(extra="forbid")

    query: str
    hits: list[HydratedHitDTO] = Field(default_factory=list)
    audit_report: LineageDedupAuditReportDTO


class LineageDefenseAuditRequestDTO(BaseModel):
    """Audit request payload comparing raw vs lineage-defended ranking."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateSessionDTO]
    include_internal: bool = False
    window_size: int = 5
    cron_weight_multiplier: float = 0.45


class LineageDefenseStatsDTO(BaseModel):
    """Aggregate dashboard metrics for lineage defense."""

    model_config = ConfigDict(extra="forbid")

    total_inspected_sessions: int
    interactive_sessions_count: int
    cron_sessions_count: int
    internal_workers_count: int
    average_token_savings_percent: float
    recall_blindness_defense_active: bool
