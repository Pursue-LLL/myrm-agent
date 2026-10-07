"""
[POS] app/schemas/memory_subagent_isolation.py
[INPUT] pydantic
[OUTPUT] FlushItemDTO, FlushResultDTO, RegisterPendingFlushRequestDTO, ExecutePreCompressionFlushRequestDTO, EphemeralMemoryOverlaySpecDTO, SubagentMemoryPolicyDTO, CreateSubagentOverlayRequestDTO, AppendSubagentEphemeralRequestDTO, MergeSelectiveRequestDTO, StatelessCronSanitizeRequestDTO, StatelessCronSanitizeResponseDTO

Pydantic DTOs for Adaptive Subagent Memory Isolation and Context Compression Flush Protocol.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FlushItemDTO(BaseModel):
    """Data transfer object representing an ephemeral or candidate memory item to be flushed."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(..., description="Unique identifier for the memory item")
    category: str = Field(..., description="Item category (e.g. user_preference, architectural_constraint)")
    content: str = Field(..., description="Text content of the memory item")
    source_turn: int = Field(default=0, ge=0, description="Conversation turn index where item originated")
    importance_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Importance or priority weight")
    tags: list[str] = Field(default_factory=list, description="Categorical or semantic tagging labels")
    created_at: str = Field(default="", description="ISO 8601 creation timestamp")


class FlushResultDTO(BaseModel):
    """Response capturing the execution telemetry of a pre-compression memory flush operation."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session or conversation ID")
    reason: str = Field(..., description="Trigger reason (compression, subagent_spawn, session_closing, manual)")
    is_success: bool = Field(..., description="True if flush operation committed successfully")
    flushed_items_count: int = Field(..., ge=0, description="Total count of items persisted")
    flushed_categories: list[str] = Field(default_factory=list, description="List of unique categories flushed")
    timestamp: str = Field(..., description="ISO 8601 timestamp of execution")
    error_message: str = Field(default="", description="Diagnostic error details if failed")


class RegisterPendingFlushRequestDTO(BaseModel):
    """Payload to buffer transient items pending pre-compression flush."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session ID")
    items: list[FlushItemDTO] = Field(..., description="List of memory items to register")


class ExecutePreCompressionFlushRequestDTO(BaseModel):
    """Payload to trigger pre-compression memory flush gate."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session ID")
    reason: str = Field(default="compression", description="Trigger reason")


class EphemeralMemoryOverlaySpecDTO(BaseModel):
    """Specification defining a subagent's ephemeral memory overlay sandboxing."""

    model_config = ConfigDict(extra="forbid")

    overlay_id: str = Field(..., description="Unique ID for the subagent overlay")
    parent_session_id: str = Field(..., description="Originating parent session ID")
    allow_selective_merge: bool = Field(default=True, description="True if core findings can be merged back")
    auto_purge_on_finish: bool = Field(default=True, description="True to purge scratch overlay on task completion")
    max_overlay_items: int = Field(default=50, gt=0, description="Capacity limit for ephemeral scratch items")


class SubagentMemoryPolicyDTO(BaseModel):
    """Policy rules governing subagent memory access boundaries."""

    model_config = ConfigDict(extra="forbid")

    isolation_scope: str = Field(default="subagent_overlay", description="Isolation scope mode")
    allow_profile_read: bool = Field(default=True, description="True to inherit parent snapshot read-only view")
    allow_ephemeral_write: bool = Field(default=True, description="True to allow writing scratch items to overlay")
    auto_purge: bool = Field(default=True, description="True to drop scratch items after task finishes")


class CreateSubagentOverlayRequestDTO(BaseModel):
    """Request payload to instantiate a subagent memory isolation sandbox."""

    model_config = ConfigDict(extra="forbid")

    spec: EphemeralMemoryOverlaySpecDTO = Field(..., description="Overlay specification")
    parent_items: list[FlushItemDTO] = Field(default_factory=list, description="Parent memory items snapshot")
    policy: SubagentMemoryPolicyDTO | None = Field(default=None, description="Optional security policy override")


class AppendSubagentEphemeralRequestDTO(BaseModel):
    """Request payload to write a transient item into subagent overlay."""

    model_config = ConfigDict(extra="forbid")

    overlay_id: str = Field(..., description="Target overlay ID")
    item: FlushItemDTO = Field(..., description="Transient scratch item to append")


class MergeSelectiveRequestDTO(BaseModel):
    """Request payload to harvest key insights from subagent overlay back to parent."""

    model_config = ConfigDict(extra="forbid")

    overlay_id: str = Field(..., description="Target overlay ID")
    selected_item_ids: list[str] = Field(..., description="IDs of high-value items to merge")


class StatelessCronSanitizeRequestDTO(BaseModel):
    """Request payload to cleanse prompt for stateless automated task execution."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Automated task ID")
    task_name: str = Field(..., description="Automated task name")
    raw_prompt: str = Field(..., description="Original raw prompt potentially containing user profile artifacts")
    strip_user_profile: bool = Field(default=True, description="True to strip user profile & dialectic mind blocks")
    require_self_contained: bool = Field(default=True, description="True to enforce self-containment checks")


class StatelessCronSanitizeResponseDTO(BaseModel):
    """Response returning cleansed self-contained prompt for automated task execution."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Target task ID")
    sanitized_prompt: str = Field(..., description="Sanitized self-contained prompt string")
    was_modified: bool = Field(..., description="True if profile blocks were stripped")
    is_self_contained: bool = Field(..., description="True if prompt meets self-containment criteria")
