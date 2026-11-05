"""[INPUT]
- pydantic::BaseModel (POS: request/response model base)

[OUTPUT]
- MemoryCommandInfluenceRef, MemoryCommandInfluenceItem, MemoryCommandCostProfile, MemoryCommandTurnEconomics, MemoryCommandParasiticMemory, MemoryCommandEconomicsDashboard

[POS]
Memory command center schemas: memory economics: influence attribution, cost profile, turn economics and parasitic memory.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MemoryCommandInfluenceRef(BaseModel):
    """A memory reference that influenced an answer or runtime decision."""

    memory_id: str
    memory_type: str
    score: float | None = None
    content_preview: str = ""
    primary_namespace: str | None = None
    source_chat_id: str | None = None
    source_message_id: str | None = None
    reason: str | None = None


class MemoryCommandInfluenceItem(BaseModel):
    """Message-level memory influence evidence."""

    id: str
    chat_id: str | None = None
    message_id: str | None = None
    occurred_at: datetime
    answer_preview: str = ""
    influence_refs: list[MemoryCommandInfluenceRef] = Field(default_factory=list)
    prompt_tokens: int = 0
    cached_tokens: int = 0


class MemoryCommandCostProfile(BaseModel):
    """Prompt injection, three-phase latency and cache impact summary."""

    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    cited_memory_refs: int = 0
    estimated_memory_tokens: int = 0
    cache_friendly: bool = True
    construction_ms: float = 0.0
    retrieval_ms: float = 0.0
    injection_overhead_ms: float = 0.0
    effective_cited_tokens: int = 0
    background_construction_tokens: int = 0
    cache_preservation_score: float = 0.0
    roi_percentage: float = 0.0
    roi_grade: str = "healthy"
    parasitic_memory_count: int = 0


class MemoryCommandTurnEconomics(BaseModel):
    """Per-turn economics metrics for long-horizon task trajectory."""

    turn_index: int
    message_id: str | None = None
    injected_tokens: int = 0
    cited_tokens: int = 0
    cached_tokens: int = 0
    roi_percentage: float = 0.0
    cache_aligned: bool = True
    retrieval_ms: float = 0.0


class MemoryCommandParasiticMemory(BaseModel):
    """Identified low-yield, high-overhead parasitic memory candidate."""

    memory_id: str
    memory_type: str = "semantic"
    content_preview: str = ""
    injected_turns_count: int = 0
    cited_turns_count: int = 0
    wasted_tokens_estimated: int = 0
    suggested_action: Literal["archive", "suppress", "review"] = "archive"


class MemoryCommandEconomicsDashboard(BaseModel):
    """Full-featured economics analytics dashboard for long-horizon sessions."""

    cost_profile: MemoryCommandCostProfile
    turn_trajectories: list[MemoryCommandTurnEconomics] = Field(default_factory=list)
    parasitic_memories: list[MemoryCommandParasiticMemory] = Field(default_factory=list)
    estimated_cost_savings_usd: float = 0.0
    recommendations: list[str] = Field(default_factory=list)
