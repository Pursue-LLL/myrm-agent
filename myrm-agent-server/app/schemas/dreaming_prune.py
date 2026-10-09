"""[POS]: app/schemas/dreaming_prune.py
[INPUT]: HTTP requests for autonomous dreaming consolidation and memory pruning.
[OUTPUT]: Pydantic schemas for dreaming execution, pruned memory audit records, and synthesis reports.
"""

from pydantic import BaseModel, Field


class MemoryItemPayload(BaseModel):
    """Memory item candidate within a session fragment."""

    id: str | None = None
    memory_id: str | None = None
    content: str = Field(..., min_length=1)
    confidence: float = 0.8
    evidence: list[dict[str, str]] = Field(default_factory=list)


class DreamingFragmentPayload(BaseModel):
    """Chat session fragment payload for dreaming consolidation."""

    session_id: str
    memories: list[MemoryItemPayload] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)
    chat_turn_count: int = 0
    project_id: str | None = None


class DreamingRunPruneRequest(BaseModel):
    """Request payload to trigger autonomous dreaming and pruning synthesis."""

    fragments: list[DreamingFragmentPayload] = Field(default_factory=list)
    raw_memories: list[MemoryItemPayload] = Field(default_factory=list)
    target_project_id: str | None = None


class PrunedRecordDTO(BaseModel):
    """Audit record for a memory pruned during dreaming consolidation."""

    memory_id: str
    decision: str
    reason: str
    superseded_by_statement: str | None = None
    pruned_at: str


class SynthesizedInsightDTO(BaseModel):
    """Synthesized cross-session cognitive insight."""

    entry_id: str
    cognitive_statement: str
    source_session_ids: list[str]
    evidence_snippets: list[str]
    confidence_delta: float
    status: str
    created_at: str
    project_id: str | None = None


class DreamingRunPruneResponse(BaseModel):
    """Response report for an autonomous dreaming and pruning cycle."""

    run_id: str
    timestamp: str
    duration_ms: float
    candidate_count: int
    synthesized_count: int
    pruned_count: int
    synthesized_insights: list[SynthesizedInsightDTO]
    pruned_records: list[PrunedRecordDTO]
