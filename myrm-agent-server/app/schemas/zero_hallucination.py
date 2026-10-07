"""Pydantic V2 DTO schemas for zero-hallucination memory retrieval and state diagnostics.

[POS]
app/schemas/zero_hallucination.py
Defines typed request/response schemas for zero-hallucination memory diagnostics,
evaluating retrieved facts against explicit error/empty states and returning boundary guardrails.

[INPUT]
- pydantic: BaseModel, ConfigDict, Field

[OUTPUT]
- MemoryFactItemDTO, ZeroHallucinationQueryRequest, ZeroHallucinationQueryResponse
- SubsystemStatusDTO, ZeroHallucinationHealthResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MemoryFactItemDTO(BaseModel):
    """Individual retrieved memory fact item."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique fact identifier.")
    text: str = Field(..., description="The textual fact content.")
    category: str = Field(default="preference", description="Category of fact (profile, rule, preference).")
    score: float = Field(default=1.0, ge=0.0, le=1.0, description="Relevance or confidence score.")



class ZeroHallucinationQueryRequest(BaseModel):
    """Request payload to query memory with strict zero-hallucination assertion."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Target query string.")
    session_id: str | None = Field(default=None, description="Optional active session identifier.")
    simulate_offline: bool = Field(default=False, description="Simulate primary memory store offline error.")
    simulated_degraded_sources: list[str] = Field(
        default_factory=list,
        description="Optional list of subsystem source names to simulate as degraded/failed.",
    )


class ZeroHallucinationQueryResponse(BaseModel):
    """Response returning evaluated memory facts and anti-hallucination prompt guardrails."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Echoed query.")
    state: str = Field(..., description="Evaluated state: FOUND, EXPLICIT_EMPTY, SERVICE_UNAVAILABLE, PARTIAL_DEGRADED.")
    total_matched: int = Field(..., description="Number of valid surviving facts.")
    facts: list[MemoryFactItemDTO] = Field(default_factory=list, description="List of matched memory facts.")
    guard_instruction: str = Field(..., description="Direct anti-fabrication prompt instruction.")
    wrapped_context: str = Field(..., description="Context wrapped in defensive boundary markers.")
    degraded_sources: list[str] = Field(default_factory=list, description="Subsystems that failed during query.")
    error_code: str | None = Field(default=None, description="Explicit error code if failed or offline.")
    is_degraded: bool = Field(..., description="Whether memory retrieval was degraded or partially failed.")


class SubsystemStatusDTO(BaseModel):
    """Health status of an individual memory subsystem component."""

    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(..., description="Component name (sqlite_relational, qdrant_vector, etc.).")
    is_online: bool = Field(..., description="Whether component is operational.")
    error_message: str | None = Field(default=None, description="Error reason if offline.")
    latency_ms: float = Field(default=0.0, ge=0.0, description="Observed query latency in ms.")


class ZeroHallucinationHealthResponse(BaseModel):
    """Response reporting overall health across memory retrieval subsystems."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="Overall status: HEALTHY, PARTIAL_DEGRADED, or UNHEALTHY.")
    total_subsystems: int = Field(..., description="Total monitored memory subsystems.")
    online_count: int = Field(..., description="Count of operational subsystems.")
    degraded_sources: list[str] = Field(default_factory=list, description="Names of failing subsystems.")
    subsystems: list[SubsystemStatusDTO] = Field(default_factory=list, description="Component-level breakdown.")
