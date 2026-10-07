# [POS]: app/schemas/fact_supersession.py
# [INPUT]: None (Pydantic models for Fact Supersession and Temporal Validity)
# [OUTPUT]: TemporalFactRecordDTO, RegisterFactRequest, RegisterFactResponse, TimeTravelRecallRequest, DialecticRecallResponseDTO, QuarantineItemDTO, ResolveQuarantineRequest, FactHistoryResponseDTO

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TemporalFactRecordDTO(BaseModel):
    """DTO representing a temporal fact with validity intervals and supersession linkage."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    subject: str
    predicate: str
    object_value: str
    valid_from: str
    valid_until: str | None = None
    superseded_by: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = Field(default="active", description="active, superseded, quarantined, archived")
    source_session_id: str | None = None
    evidence_quote: str | None = None
    created_at: str | None = None


class RegisterFactRequest(BaseModel):
    """Request payload to register a factual assertion."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(..., description="Subject entity name")
    predicate: str = Field(..., description="Predicate relationship or attribute")
    object_value: str = Field(..., description="Value or statement asserted")
    valid_from: str = Field(..., description="ISO timestamp marking beginning of validity")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_session_id: str | None = None
    evidence_quote: str | None = None


class RegisterFactResponse(BaseModel):
    """Response payload returned when ingesting a factual assertion."""

    model_config = ConfigDict(extra="forbid")

    action_taken: str = Field(..., description="RECORDED, SUPERSEDED, or QUARANTINED")
    fact: TemporalFactRecordDTO | None = None
    quarantine_id: str | None = None


class TimeTravelRecallRequest(BaseModel):
    """Request payload for dialectic recall with point-in-time time-travel support."""

    model_config = ConfigDict(extra="forbid")

    subject: str | None = None
    predicate: str | None = None
    as_of_time: str | None = Field(
        default=None,
        description="Optional ISO timestamp for time-travel query. If None, queries active state.",
    )


class DialecticRecallResponseDTO(BaseModel):
    """Explainable recall payload containing active facts and historical supersession lineage."""

    model_config = ConfigDict(extra="forbid")

    active_facts: list[TemporalFactRecordDTO]
    superseded_lineage: dict[str, list[TemporalFactRecordDTO]]
    as_of_time: str | None = None
    total_matched: int


class QuarantineItemDTO(BaseModel):
    """DTO representing a contradictory fact quarantined awaiting human audit."""

    model_config = ConfigDict(extra="forbid")

    quarantine_id: str
    new_fact: TemporalFactRecordDTO
    conflicting_fact_id: str
    conflict_score: float
    detected_at: str
    status: str


class ResolveQuarantineRequest(BaseModel):
    """Request payload for human resolution of quarantined contradictions."""

    model_config = ConfigDict(extra="forbid")

    approve_override: bool = Field(
        ...,
        description="True to approve candidate and supersede conflicting fact; False to reject.",
    )


class FactHistoryResponseDTO(BaseModel):
    """Response payload containing backward ancestor facts superseded leading to this fact."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    ancestor_facts: list[TemporalFactRecordDTO]
