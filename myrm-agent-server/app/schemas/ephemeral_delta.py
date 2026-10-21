"""DTOs for prompt cache preserving ephemeral delta memory suite.

[POS]
app/schemas/ephemeral_delta.py

[INPUT]
- pydantic BaseModel, Field, ConfigDict, typing literals

[OUTPUT]
- DTOs for prompt cache preserving ephemeral delta memory suite
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DeltaActionDTO = Literal["override", "add_fact", "revoke"]
DeltaSourceDTO = Literal["user_explicit", "agent_inferred"]


class EphemeralDeltaItemDTO(BaseModel):
    """An active ephemeral delta record mounted without breaking prompt prefix cache."""

    model_config = ConfigDict(extra="forbid")

    delta_id: str
    session_id: str
    target_key: str
    content: str
    action: DeltaActionDTO = "override"
    turn_index: int = Field(default=1, ge=0)
    source: DeltaSourceDTO = "user_explicit"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime
    is_reconciled: bool = False


class RecordDeltaRequestDTO(BaseModel):
    """Payload to record an in-flight session correction delta."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    target_key: str
    content: str
    action: DeltaActionDTO = "override"
    turn_index: int = Field(default=1, ge=0)
    source: DeltaSourceDTO = "user_explicit"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SessionDeltaSnapshotDTO(BaseModel):
    """Snapshot of session in-flight deltas and reconciliation status."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    active_deltas: list[EphemeralDeltaItemDTO] = Field(default_factory=list)
    is_reconciled: bool = False
    reconciled_at: datetime | None = None


class ReconcileSessionResponseDTO(BaseModel):
    """Read-only session delta status (durable memory writes use the memory store on agent turns)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    active_delta_count: int = Field(ge=0)
    injection_still_active: bool = True


class PromptCacheMetricsDTO(BaseModel):
    """Layout diagnostics for ephemeral deltas (provider cache hits use chat health / trace SSOT)."""

    model_config = ConfigDict(extra="forbid")

    system_prompt_frozen: bool
    system_prompt_byte_hash: str | None = None
    in_flight_deltas_count: int = Field(ge=0)
    recency_perception_delay_ms: float | None = Field(default=None, ge=0.0)
    kv_cache_hit_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    avoided_recomputation_tokens: int | None = Field(default=None, ge=0)


class PreviewDeltaInjectionRequestDTO(BaseModel):
    """Request payload to simulate multi-turn message injection."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    raw_system_prompt: str = Field(default="You are Myrm Agent. System Profile: Senior Architect.")
    human_messages: list[str] = Field(
        default_factory=lambda: [
            "Hello, please inspect my repo.",
            "Please call me Old Zhang instead.",
        ]
    )


class PreviewDeltaInjectionResponseDTO(BaseModel):
    """Response payload visualizing frozen System Prompt vs HumanMessage tail augmentation."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    frozen_system_prompt: str
    augmented_final_human_message: str
    tail_tag_snippet: str
    active_deltas: list[EphemeralDeltaItemDTO] = Field(default_factory=list)
    metrics: PromptCacheMetricsDTO


# Backwards compatibility and alternative naming aliases
RecordEphemeralDeltaRequest = RecordDeltaRequestDTO
EphemeralDeltaBufferSnapshotDTO = SessionDeltaSnapshotDTO
ReconcileSessionResponse = ReconcileSessionResponseDTO
