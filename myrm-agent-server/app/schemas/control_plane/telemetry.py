"""[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- ContextCompactionTelemetryEnvelope, ContextCompactionBatchPayload, MemoryBriefStatusTelemetryAggregate, MemoryBriefStatusDroppedAggregate, MemoryBriefStatusTelemetryEnvelope, MemoryBriefStatusBatchPayload, MemoryGuardianGuardTelemetryAggregate, MemoryGuardianGuardTelemetryEnvelope, MemoryGuardianGuardBatchPayload

[POS]
Control-plane schemas: compaction and memory telemetry envelopes and batch payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .context_snapshot import ContextCompactionSnapshot


class ContextCompactionTelemetryEnvelope(BaseModel):
    """Detached telemetry payload ready for transport."""

    telemetry_subject: str
    chat_id: str
    timestamp: str
    snapshot: ContextCompactionSnapshot


class ContextCompactionBatchPayload(BaseModel):
    """Batch payload for context compaction telemetry."""

    events: list[ContextCompactionTelemetryEnvelope]


class MemoryBriefStatusTelemetryAggregate(BaseModel):
    """Aggregated memory brief status labels for a flush window."""

    phase: str
    brief_state: str
    brief_reason: str
    brief_source: str
    injection_state: str
    injection_source: str
    injection_reason: str
    count: int = 0


class MemoryBriefStatusDroppedAggregate(BaseModel):
    """Aggregated drop labels for memory brief telemetry backpressure events."""

    dropped_phase: str
    incoming_phase: str
    count: int = 0


class MemoryBriefStatusTelemetryEnvelope(BaseModel):
    """Detached aggregated telemetry payload for memory brief statuses."""

    telemetry_subject: str
    envelope_id: str = Field(min_length=1, max_length=128)
    timestamp: str
    aggregates: list[MemoryBriefStatusTelemetryAggregate]
    dropped_aggregates: list[MemoryBriefStatusDroppedAggregate] = Field(default_factory=list)

    @field_validator("envelope_id")
    @classmethod
    def _validate_envelope_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("envelope_id must not be blank")
        return normalized


class MemoryBriefStatusBatchPayload(BaseModel):
    """Batch payload for memory brief status telemetry."""

    events: list[MemoryBriefStatusTelemetryEnvelope]


class MemoryGuardianGuardTelemetryAggregate(BaseModel):
    """Aggregated guard-unavailable labels for one flush window."""

    reason: str = Field(min_length=1, max_length=64)
    guard: str = Field(min_length=1, max_length=32)
    frequency_tier: str = Field(min_length=1, max_length=32)
    quiet_window_enabled: bool
    count: int = 0

    @field_validator("reason", "guard", "frequency_tier")
    @classmethod
    def _validate_guard_labels(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("guardian guard telemetry labels must not be blank")
        return normalized


class MemoryGuardianGuardTelemetryEnvelope(BaseModel):
    """Detached aggregated telemetry payload for guardian guard-unavailable events."""

    telemetry_subject: str
    envelope_id: str = Field(min_length=1, max_length=128)
    timestamp: str
    aggregates: list[MemoryGuardianGuardTelemetryAggregate]

    @field_validator("envelope_id")
    @classmethod
    def _validate_guard_envelope_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("envelope_id must not be blank")
        return normalized


class MemoryGuardianGuardBatchPayload(BaseModel):
    """Batch payload for guardian guard-unavailable telemetry."""

    events: list[MemoryGuardianGuardTelemetryEnvelope]
