"""Pydantic V2 schemas for bitemporal truth maintenance API.

[POS]
Data transfer objects and request/response models for bitemporal coordinate tracking,
non-destructive evidence retraction, justification graph reasoning, and temporal querying.

[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- TimeIntervalDTO
- BitemporalCoordinatesDTO
- EvidenceRecordDTO
- RecordFactRequest
- DeriveInferenceRequest
- RetractRecordRequest
- RetractRecordResponse
- TemporalQueryRequest
- TemporalQueryResponse
- SnapshotRequest
- SnapshotResponse
- BitemporalTmsHealthResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class TimeIntervalDTO(BaseModel):
    """Half-open temporal interval [start, end)."""

    start: float = Field(description="Inclusive starting timestamp")
    end: float | None = Field(default=None, description="Exclusive ending timestamp (None for +inf)")


class BitemporalCoordinatesDTO(BaseModel):
    """Dual-timeline coordinates representing valid world time and system transaction time."""

    valid_interval: TimeIntervalDTO = Field(description="Temporal range when fact is true in world")
    known_interval: TimeIntervalDTO = Field(description="Temporal range when system believes the fact")


class EvidenceRecordDTO(BaseModel):
    """Normalized evidence record representation."""

    evidence_id: str = Field(description="Unique identifier for evidence node")
    content: str = Field(description="Descriptive assertion statement")
    evidence_type: str = Field(description="Type: fact, observation, inference, decision")
    bitemporal: BitemporalCoordinatesDTO = Field(description="Bitemporal coordinate pair")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Assertion confidence score")
    metadata: dict[str, str] = Field(default_factory=dict, description="Arbitrary metadata key-values")


class RecordFactRequest(BaseModel):
    """Request to record a ground truth fact with bitemporal boundaries."""

    evidence_id: str = Field(description="Target evidence identifier")
    content: str = Field(description="Assertion statement content")
    valid_start: float = Field(description="Timestamp from which fact is valid in reality")
    valid_end: float | None = Field(default=None, description="Timestamp until which fact is valid (or None)")
    known_start: float | None = Field(default=None, description="System transaction timestamp (or now)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence level")
    metadata: dict[str, str] = Field(default_factory=dict, description="Additional metadata")

    @model_validator(mode="after")
    def validate_interval(self) -> RecordFactRequest:
        if self.valid_end is not None and self.valid_start > self.valid_end:
            raise ValueError(
                f"valid_start ({self.valid_start}) cannot exceed valid_end ({self.valid_end})"
            )
        return self


class DeriveInferenceRequest(BaseModel):
    """Request to derive a supported inference from premises."""

    inference_id: str = Field(description="Target inference identifier")
    content: str = Field(description="Inference conclusion statement")
    premise_ids: list[str] = Field(min_length=1, description="List of premise evidence IDs supporting inference")
    justification: str = Field(description="Reasoning explanation justifying inference")
    valid_start: float | None = Field(default=None, description="Valid start timestamp (or now)")
    valid_end: float | None = Field(default=None, description="Valid end timestamp (or None)")
    known_start: float | None = Field(default=None, description="Known start timestamp (or now)")
    causal_distance: int = Field(default=1, ge=1, description="Topological distance from premises")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence level")
    metadata: dict[str, str] = Field(default_factory=dict, description="Additional metadata")

    @model_validator(mode="after")
    def validate_interval(self) -> DeriveInferenceRequest:
        if (
            self.valid_start is not None
            and self.valid_end is not None
            and self.valid_start > self.valid_end
        ):
            raise ValueError(
                f"valid_start ({self.valid_start}) cannot exceed valid_end ({self.valid_end})"
            )
        return self


class RetractRecordRequest(BaseModel):
    """Request to non-destructively retract an evidence record."""

    evidence_id: str = Field(description="Identifier of evidence record to retract")
    retracted_at: float | None = Field(default=None, description="Retraction timestamp (or now)")


class RetractRecordResponse(BaseModel):
    """Verdict of evidence record retraction."""

    success: bool = Field(description="Whether the retraction succeeded")
    evidence_id: str = Field(description="Target evidence identifier")
    retracted_at: float = Field(description="Recorded retraction timestamp")


class TemporalQueryRequest(BaseModel):
    """Request to query active memories as of specified bitemporal point."""

    as_of_valid_time: float | None = Field(default=None, description="Query coordinate in world timeline")
    as_of_known_time: float | None = Field(default=None, description="Query coordinate in system belief timeline")
    require_active_support: bool = Field(default=True, description="Strictly filter by active justifications")
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold")
    evidence_types: list[str] | None = Field(default=None, description="Optional evidence type filter")


class TemporalQueryResponse(BaseModel):
    """Filtered list of active memory records at target bitemporal point."""

    total: int = Field(description="Count of matched active records")
    records: list[EvidenceRecordDTO] = Field(default_factory=list, description="Matched records")
    as_of_valid_time: float = Field(description="Evaluated valid time")
    as_of_known_time: float = Field(description="Evaluated known time")


class SnapshotRequest(BaseModel):
    """Request to project a comprehensive bitemporal truth maintenance snapshot."""

    as_of_valid_time: float | None = Field(default=None, description="Target valid time")
    as_of_known_time: float | None = Field(default=None, description="Target known time")


class SnapshotResponse(BaseModel):
    """Projected snapshot partitioning active vs invalidated entities."""

    active_evidences: list[EvidenceRecordDTO] = Field(default_factory=list)
    retracted_evidences: list[EvidenceRecordDTO] = Field(default_factory=list)
    active_inferences: list[EvidenceRecordDTO] = Field(default_factory=list)
    invalidated_inferences: list[EvidenceRecordDTO] = Field(default_factory=list)
    as_of_valid_time: float = Field(description="Evaluated valid time")
    as_of_known_time: float = Field(description="Evaluated known time")
    total_count: int = Field(description="Total entity count across all partitions")


class BitemporalTmsHealthResponse(BaseModel):
    """Health status probe response for bitemporal TMS subsystem."""

    status: str = Field(default="ok")
    module: str = Field(default="bitemporal_truth_maintenance")
    version: str = Field(default="1.0.0")
