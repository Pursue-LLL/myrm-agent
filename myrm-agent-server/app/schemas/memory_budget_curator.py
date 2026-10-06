"""
[POS] app/schemas/memory_budget_curator.py
[INPUT] pydantic
[OUTPUT] ManagedMemoryItemDTO, MemoryBudgetSpecDTO, MemoryBudgetStatusDTO, MemoryBatchOperationDTO, AtomicBatchRequestDTO, AtomicBatchResponseDTO, ScrollMessageItemDTO, ScrollAnchorRequestDTO, ScrollAnchorResponseDTO

Pydantic DTOs for Dual-Track Volatile Snapshot Memory Budget Meter, Atomic Operations Curator, and Session Scroll Navigator.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ManagedMemoryItemDTO(BaseModel):
    """Managed individual memory item subject to budget metering."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(..., description="Unique memory item ID")
    content: str = Field(..., description="Memory factual text content")
    token_count: int = Field(default=0, ge=0, description="Estimated token consumption")


class MemoryBudgetSpecDTO(BaseModel):
    """Specification defining memory token and slot allocation limits."""

    model_config = ConfigDict(extra="forbid")

    max_tokens: int = Field(default=2500, gt=0, description="Maximum total tokens budgeted")
    max_slots: int = Field(default=20, gt=0, description="Maximum number of memory slots")
    warning_threshold_pct: float = Field(
        default=80.0, ge=0.0, le=100.0, description="Warning threshold percentage"
    )


class MemoryBudgetStatusDTO(BaseModel):
    """Live telemetry descriptor of current memory budget utilization."""

    model_config = ConfigDict(extra="forbid")

    used_tokens: int = Field(..., ge=0, description="Tokens consumed")
    max_tokens: int = Field(..., gt=0, description="Tokens maximum limit")
    token_usage_pct: float = Field(..., ge=0.0, description="Token usage percentage")
    used_slots: int = Field(..., ge=0, description="Slots consumed")
    max_slots: int = Field(..., gt=0, description="Slots maximum limit")
    slot_usage_pct: float = Field(..., ge=0.0, description="Slot usage percentage")
    is_warning: bool = Field(..., description="True if approaching capacity threshold")
    is_overflow: bool = Field(..., description="True if budget is strictly breached")
    budget_header_slice: str = Field(
        ..., description="Visual header formatted for prompt prefix injection"
    )


class MemoryBatchOperationDTO(BaseModel):
    """Single operation descriptor inside an atomic curation batch."""

    model_config = ConfigDict(extra="forbid")

    operation_type: str = Field(..., description="Operation type: add, remove, or replace")
    target_id: str | None = Field(default=None, description="Target item ID for remove/replace")
    target_substring: str | None = Field(
        default=None, description="Fuzzy substring target for remove/replace"
    )
    new_id: str | None = Field(default=None, description="New item ID for add/replace")
    new_content: str | None = Field(default=None, description="New text content for add/replace")
    estimated_tokens: int = Field(
        default=0, ge=0, description="Explicit tokens override (0 for auto-estimate)"
    )


class AtomicBatchRequestDTO(BaseModel):
    """Request payload executing an atomic batch of memory curation operations."""

    model_config = ConfigDict(extra="forbid")

    current_items: list[ManagedMemoryItemDTO] = Field(
        default_factory=list, description="Current memory snapshot"
    )
    operations: list[MemoryBatchOperationDTO] = Field(
        default_factory=list, description="Ordered batch of operations to apply atomically"
    )
    budget_spec: MemoryBudgetSpecDTO | None = Field(
        default=None, description="Optional custom budget constraints"
    )


class AtomicBatchResponseDTO(BaseModel):
    """Response returned upon committing or rolling back an atomic curation batch."""

    model_config = ConfigDict(extra="forbid")

    is_success: bool = Field(..., description="True if all operations succeeded without breach")
    applied_count: int = Field(..., ge=0, description="Number of committed operations")
    rolled_back: bool = Field(..., description="True if transaction aborted to initial state")
    error_message: str = Field(default="", description="Failure justification if rolled back")
    current_budget: MemoryBudgetStatusDTO = Field(
        ..., description="Budget utilization snapshot after evaluation"
    )
    retained_items: list[ManagedMemoryItemDTO] = Field(
        default_factory=list, description="Final retained memory items"
    )


class ScrollMessageItemDTO(BaseModel):
    """Individual conversation message traversed within a sliding window."""

    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(..., description="Unique message ID")
    role: str = Field(..., description="Sender role: user, assistant, system, tool")
    content: str = Field(..., description="Message text content")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class ScrollAnchorRequestDTO(BaseModel):
    """Request traversing conversation history anchored around a target message ID."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., description="Target conversation ID")
    around_message_id: str = Field(..., description="Anchor message ID to window around")
    before_limit: int = Field(default=5, ge=0, description="Number of preceding messages")
    after_limit: int = Field(default=5, ge=0, description="Number of succeeding messages")


class ScrollAnchorResponseDTO(BaseModel):
    """Resultant bidirectional window of messages around the anchor."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., description="Conversation ID")
    around_message_id: str = Field(..., description="Anchor message ID")
    messages: list[ScrollMessageItemDTO] = Field(
        default_factory=list, description="Continuous slice of conversation messages"
    )
    has_more_before: bool = Field(..., description="True if preceding history extends further")
    has_more_after: bool = Field(..., description="True if succeeding history extends further")
