"""Pydantic V2 schemas for Visual Kanban Multi-Agent Workflow Dispatcher and Card Handoff (Item 66).

[INPUT]
- CreateCardRequest, TransitionCardRequest, UpdateProgressRequest, FlagBlockerRequest schemas.

[OUTPUT]
- KanbanCardDTO, HandoffEventDTO, KanbanWorkspaceStateDTO.

[POS]
- Server-side DTO layer for Item 66 visual kanban multi-agent workflow dispatching.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class KanbanColumnDTOEnum(enum.StrEnum):
    """The five standard workflow stages in the multi-agent kanban board."""

    BACKLOG = "backlog"
    RESEARCHING = "researching"
    DEVELOPING = "developing"
    REVIEWING = "reviewing"
    DONE = "done"


class CardHandoffStatusDTOEnum(enum.StrEnum):
    """Lifecycle and handoff state of a kanban task card."""

    IDLE = "idle"
    IN_TRANSIT = "in_transit"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class KanbanCardDTO(BaseModel):
    """DTO representing a single task card inside a kanban column."""

    model_config = ConfigDict(frozen=True)

    card_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(default="")
    column: KanbanColumnDTOEnum = Field(default=KanbanColumnDTOEnum.BACKLOG)
    assigned_agent_id: str = Field(..., min_length=1)
    progress_percent: int = Field(default=0, ge=0, le=100)
    handoff_status: CardHandoffStatusDTOEnum = Field(default=CardHandoffStatusDTOEnum.IDLE)
    handoff_payload: dict[str, str] = Field(default_factory=dict)
    blocker_reason: str | None = Field(default=None)
    created_at: float = Field(default=0.0)
    updated_at: float = Field(default=0.0)


class HandoffEventDTO(BaseModel):
    """DTO recording an automated cross-agent card handoff event."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., min_length=1)
    card_id: str = Field(..., min_length=1)
    from_agent_id: str = Field(..., min_length=1)
    to_agent_id: str = Field(..., min_length=1)
    from_column: KanbanColumnDTOEnum = Field(...)
    to_column: KanbanColumnDTOEnum = Field(...)
    context_summary: str = Field(default="")
    timestamp: float = Field(default=0.0)


class KanbanWorkspaceStateDTO(BaseModel):
    """DTO representing the aggregated state of a multi-agent kanban board workspace."""

    model_config = ConfigDict(frozen=True)

    workspace_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    cards: list[KanbanCardDTO] = Field(default_factory=list)
    handoff_history: list[HandoffEventDTO] = Field(default_factory=list)
    active_blockers: int = Field(default=0, ge=0)


class CreateCardRequest(BaseModel):
    """Payload to create a new card in the kanban workspace."""

    model_config = ConfigDict(frozen=True)

    workspace_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(default="")
    column: KanbanColumnDTOEnum = Field(default=KanbanColumnDTOEnum.BACKLOG)
    assigned_agent_id: str | None = Field(default=None)


class TransitionCardRequest(BaseModel):
    """Payload to move a card to a new column and trigger an automated agent handoff."""

    model_config = ConfigDict(frozen=True)

    target_column: KanbanColumnDTOEnum = Field(...)
    handoff_context: dict[str, str] | None = Field(default=None)
    target_agent_id: str | None = Field(default=None)


class UpdateProgressRequest(BaseModel):
    """Payload to update the execution progress percentage of a card."""

    model_config = ConfigDict(frozen=True)

    progress_percent: int = Field(..., ge=0, le=100)


class FlagBlockerRequest(BaseModel):
    """Payload to flag a card as blocked."""

    model_config = ConfigDict(frozen=True)

    reason: str = Field(..., min_length=1)
