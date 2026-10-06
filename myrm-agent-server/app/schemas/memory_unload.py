"""
[POS] app/schemas/memory_unload.py
[INPUT] pydantic
[OUTPUT] EmergencyFlushRequestDTO, EmergencyFlushResponseDTO, UnfinalizedSessionDTO, ListUnfinalizedResponseDTO, AcknowledgeSessionRequestDTO, AcknowledgeSessionResponseDTO

Pydantic DTOs for desktop and WebUI graceful flush and unload finalize guard.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EmergencyFlushRequestDTO(BaseModel):
    """Payload submitted when browser page unloads or desktop window closes."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="Active session ID to finalize gracefully")
    reason: str = Field(
        default="browser_unload",
        description="Reason for unload: browser_unload, window_close_requested, session_switch, crash_prevention",
    )
    active_goal: str | None = Field(default=None, description="Current unfulfilled or in-flight user goal")
    unsaved_notes: list[str] = Field(
        default_factory=list,
        description="Transient notes or scratchpad text present in frontend state",
    )
    recent_messages: list[dict[str, str]] = Field(
        default_factory=list,
        description="Tail of recent user/assistant conversation messages",
    )
    target_handoff_agent: str | None = Field(
        default=None,
        description="Optional designated target agent if handoff intended upon resume",
    )


class EmergencyFlushResponseDTO(BaseModel):
    """Result of emergency flush and memory finalization."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether emergency persistence succeeded")
    handoff_id: str = Field(..., description="Registered handoff ID for crash-proof resumption")
    snapshot_path: str = Field(..., description="Absolute path to markdown memorandum written on disk")
    reason: str = Field(..., description="Trigger reason recorded")
    finalized_at: float = Field(..., description="Unix timestamp of emergency finalization")


class UnfinalizedSessionDTO(BaseModel):
    """Metadata summary of an unfinalized or crash-recovered session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Session identifier")
    handoff_id: str = Field(..., description="Associated emergency handoff package ID")
    status: str = Field(..., description="Claim or finalization status: pending or claimed")
    created_at: float = Field(..., description="Unix timestamp when snapshot was captured")
    active_goal: str | None = Field(default=None, description="Active goal from preserved context")
    snapshot_path: str = Field(..., description="Absolute path to markdown snapshot file")


class ListUnfinalizedResponseDTO(BaseModel):
    """List of pending unfinalized sessions needing recovery dialog or acknowledgment."""

    model_config = ConfigDict(extra="forbid")

    unfinalized_sessions: list[UnfinalizedSessionDTO] = Field(
        default_factory=list,
        description="Collection of unfinalized sessions awaiting user restoration or acknowledgment",
    )


class AcknowledgeSessionRequestDTO(BaseModel):
    """Payload to acknowledge and mark an emergency handoff as claimed."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="Session identifier to acknowledge and dismiss")


class AcknowledgeSessionResponseDTO(BaseModel):
    """Outcome of acknowledging unfinalized session."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether session acknowledgment succeeded")
    session_id: str = Field(..., description="Acknowledged session ID")
    message: str = Field(..., description="Status summary message")
