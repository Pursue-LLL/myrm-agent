"""Schemas for safe episodic memory forget requests and probe responses.

[INPUT]
- Pydantic BaseModel, caller session parameters, memory ID specifications.

[OUTPUT]
- SafeForgetRequestDTO, SafeForgetResponseDTO, ParentProbeResponseDTO.

[POS]
- Server API contracts for Item 149 SafeEpisodicForgetSuite.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SafeForgetRequestDTO(BaseModel):
    """Payload to safely forget an episodic memory."""

    memory_id: str = Field(..., description="Unique ID of the episodic memory")
    caller_session_id: str = Field(..., description="Session ID initiating the forget action")
    user_id: str = Field(default="", description="Optional user identifier")
    allow_global: bool = Field(default=True, description="Whether global-scoped memory can be forgotten")
    reason: str = Field(default="", description="Reason or audit justification for forget request")


class SafeForgetResponseDTO(BaseModel):
    """Response containing outcome of safe episodic memory forget operation."""

    memory_id: str
    deleted: bool
    unauthorized: bool
    retained_shared_children: bool
    deleted_child_tables: list[str]
    message: str


class ParentProbeResponseDTO(BaseModel):
    """Response containing probe status of competing parents across tiers."""

    memory_id: str
    authorized: bool
    episodic_exists: bool
    competing_tiers: list[str]
    has_competing_parents: bool
