"""Control-plane schemas.

[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- Context snapshots and telemetry envelopes, re-exported for services.

[POS]
Aggregate exit of the control-plane schema package: events, snapshots and telemetry.
"""

from __future__ import annotations

from .context_events import (
    ContextArchiveRestoreBlockEventSnapshot,
    ContextArchiveRestoreOutcomeEventSnapshot,
    ContextArchiveRestoreResultEventSnapshot,
    ContextCompressionEventSnapshot,
    ContextRefetchEventSnapshot,
)
from .context_snapshot import (
    ContextCompactionSnapshot,
)
from .telemetry import (
    ContextCompactionBatchPayload,
    ContextCompactionTelemetryEnvelope,
    MemoryBriefStatusBatchPayload,
    MemoryBriefStatusDroppedAggregate,
    MemoryBriefStatusTelemetryAggregate,
    MemoryBriefStatusTelemetryEnvelope,
    MemoryGuardianGuardBatchPayload,
    MemoryGuardianGuardTelemetryAggregate,
    MemoryGuardianGuardTelemetryEnvelope,
)

__all__ = [
    "ContextCompressionEventSnapshot",
    "ContextRefetchEventSnapshot",
    "ContextArchiveRestoreBlockEventSnapshot",
    "ContextArchiveRestoreOutcomeEventSnapshot",
    "ContextArchiveRestoreResultEventSnapshot",
    "ContextCompactionSnapshot",
    "ContextCompactionTelemetryEnvelope",
    "ContextCompactionBatchPayload",
    "MemoryBriefStatusTelemetryAggregate",
    "MemoryBriefStatusDroppedAggregate",
    "MemoryBriefStatusTelemetryEnvelope",
    "MemoryBriefStatusBatchPayload",
    "MemoryGuardianGuardTelemetryAggregate",
    "MemoryGuardianGuardTelemetryEnvelope",
    "MemoryGuardianGuardBatchPayload",
]
