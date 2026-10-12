"""Schemas for cross-agent composable context, conflict arbitration, and handoff integrity.

[INPUT]
- pydantic
- typing

[OUTPUT]
- ProjectComposableContextRequestDTO
- ContextLayerDTO
- ComposableContextResponseDTO
- MemoryAssertionDTO
- ArbitrateConflictRequestDTO
- ArbitrationOutcomeDTO
- SealHandoffRequestDTO
- HandoffPacketDTO
- VerifyHandoffRequestDTO
- HandoffVerificationResponseDTO

[POS]
Data transfer contracts between frontend UI / multi-agent orchestrator and the cross-agent memory service.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class ContextLayerDTO(BaseModel):
    """Metadata and content for an individual projected context tier."""

    model_config = ConfigDict(extra="forbid")

    layer_kind: str = Field(..., description="Classification tier (private, profile, global, handoff)")
    title: str = Field(..., description="Section title")
    content: str = Field(..., description="Projected textual content")
    token_count: int = Field(ge=0, description="Estimated token count")
    content_hash: str = Field(..., description="SHA-256 fingerprint of the content")
    is_shared: bool = Field(default=False, description="Whether this layer is accessible to peer agents")


class ProjectComposableContextRequestDTO(BaseModel):
    """Request payload for composable 4-layer context projection."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Target agent receiving the projection")
    session_id: str = Field(..., description="Active session or coordination id")
    global_ground_truth: list[str] = Field(default_factory=list, description="Shared global facts")
    profile_tools_memory: list[str] = Field(default_factory=list, description="Agent persona and tools")
    private_scratchpad: str | None = Field(default=None, description="Confidential private notes")
    token_budget: int = Field(default=4096, ge=256, le=32768, description="Target token budget ceiling")


class ComposableContextResponseDTO(BaseModel):
    """Response payload containing assembled context and KV cache fingerprint."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(...)
    session_id: str = Field(...)
    total_tokens: int = Field(ge=0)
    layers: list[ContextLayerDTO] = Field(default_factory=list)
    assembled_prompt_text: str = Field(...)
    cache_prefix_hash: str = Field(...)


class MemoryAssertionDTO(BaseModel):
    """Atomic fact asserted by an agent."""

    model_config = ConfigDict(extra="forbid")

    assertion_id: str = Field(..., description="Unique claim identifier")
    subject: str = Field(..., description="Entity or topic name")
    predicate: str = Field(..., description="Relation or property")
    object_value: str = Field(..., description="Claimed value")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence asserted")
    source_agent_id: str = Field(..., description="Author agent id")
    source_reference: str | None = Field(default=None, description="Physical code path or tool reference")
    timestamp: float = Field(default_factory=time.time, description="Creation timestamp")


class ArbitrateConflictRequestDTO(BaseModel):
    """Request payload for settling factual divergences between two agents."""

    model_config = ConfigDict(extra="forbid")

    divergence_id: str | None = Field(default=None, description="Optional incident ID")
    subject: str = Field(..., description="Contested subject")
    predicate: str = Field(..., description="Contested predicate")
    assertion_a: MemoryAssertionDTO = Field(..., description="First agent assertion")
    assertion_b: MemoryAssertionDTO = Field(..., description="Second agent assertion")
    workspace_root: str | None = Field(default=None, description="Physical workspace root for ground truth probing")


class ArbitrationOutcomeDTO(BaseModel):
    """Result of multi-agent conflict settlement."""

    model_config = ConfigDict(extra="forbid")

    divergence_id: str = Field(...)
    resolved: bool = Field(...)
    policy_applied: str = Field(...)
    winning_assertion: MemoryAssertionDTO = Field(...)
    audit_rationale: str = Field(...)
    requires_human_confirmation: bool = Field(default=False)


class SealHandoffRequestDTO(BaseModel):
    """Request payload to seal an outgoing task handoff packet."""

    model_config = ConfigDict(extra="forbid")

    source_agent_id: str = Field(...)
    target_agent_id: str = Field(...)
    task_id: str = Field(...)
    context_snapshot: str = Field(...)
    critical_assertions: list[MemoryAssertionDTO] = Field(default_factory=list)
    secret_salt: str = Field(default="")


class HandoffPacketDTO(BaseModel):
    """Signed task handoff transfer packet."""

    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(...)
    source_agent_id: str = Field(...)
    target_agent_id: str = Field(...)
    task_id: str = Field(...)
    context_snapshot: str = Field(...)
    critical_assertions: list[MemoryAssertionDTO] = Field(default_factory=list)
    timestamp: float = Field(...)
    signature_sha256: str = Field(...)


class VerifyHandoffRequestDTO(BaseModel):
    """Request payload to verify the integrity seal of an incoming handoff packet."""

    model_config = ConfigDict(extra="forbid")

    packet: HandoffPacketDTO = Field(...)
    secret_salt: str = Field(default="")


class HandoffVerificationResponseDTO(BaseModel):
    """Verification outcome of incoming handoff packet."""

    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(...)
    is_valid: bool = Field(...)
    verified_assertions_count: int = Field(ge=0)
    rejection_reason: str | None = Field(default=None)
