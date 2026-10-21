"""Pydantic V2 DTO schemas for Visual Multi-Agent Kanban Orchestrator and Card Lifecycle Dispatcher."""

from __future__ import annotations

from enum import StrEnum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class KanbanLaneEnum(StrEnum):
    """Kanban swimlane columns."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"


class CardPriorityEnum(StrEnum):
    """Task card priority rating."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CardArtifactDTO(BaseModel):
    """Mounted artifact record on a Kanban card."""

    artifact_id: str = Field(..., description="Unique artifact ID")
    name: str = Field(..., description="Artifact title or file name")
    artifact_type: str = Field(default="file", description="Type (diff, file, report, test_result)")
    file_path: Optional[str] = Field(default=None, description="Workspace file path")
    content_preview: Optional[str] = Field(default=None, description="Preview of diff or content")
    mounted_at: float = Field(..., description="Epoch timestamp of mounting")


class KanbanCardDTO(BaseModel):
    """Persistent task card with dependency DAG tracking and card-scoped sandbox path."""

    card_id: str = Field(..., description="Unique card ID")
    board_id: str = Field(..., description="Parent board ID")
    title: str = Field(..., description="Task title")
    description: str = Field(default="", description="Task specification")
    lane: KanbanLaneEnum = Field(default=KanbanLaneEnum.BACKLOG, description="Current swimlane column")
    priority: CardPriorityEnum = Field(default=CardPriorityEnum.MEDIUM, description="Task urgency level")
    assigned_agent: str = Field(..., description="Assigned specialist Agent handle (e.g. @backend-dev)")
    depends_on: List[str] = Field(default_factory=list, description="Prerequisite card IDs")
    blocked_by: List[str] = Field(default_factory=list, description="IDs of unresolved dependencies")
    sandbox_subdir: str = Field(..., description="Card-scoped isolated directory (e.g. tasks/card-8f12)")
    artifacts: List[CardArtifactDTO] = Field(default_factory=list, description="Mounted outputs")
    created_at: float = Field(..., description="Creation epoch timestamp")
    updated_at: float = Field(..., description="Last modification epoch timestamp")
    completed_at: Optional[float] = Field(default=None, description="Completion epoch timestamp")


class KanbanBoardStateDTO(BaseModel):
    """Full projection of a multi-agent Kanban board."""

    board_id: str = Field(..., description="Unique board ID")
    session_id: str = Field(..., description="Parent chat session ID")
    title: str = Field(..., description="Project board title")
    cards: Dict[str, KanbanCardDTO] = Field(default_factory=dict, description="Lookup map of cards by card_id")
    created_at: float = Field(..., description="Board creation epoch timestamp")
    updated_at: float = Field(..., description="Last board update epoch timestamp")


class CreateBoardRequestDTO(BaseModel):
    """Payload to create a new multi-agent project board."""

    session_id: str = Field(..., description="Chat session ID to bind this board to")
    title: str = Field(..., min_length=1, max_length=120, description="Board title")


class CreateCardRequestDTO(BaseModel):
    """Payload to create a new task card."""

    title: str = Field(..., min_length=1, max_length=160, description="Card task title")
    description: str = Field(default="", description="Detailed instruction for assigned specialist")
    assigned_agent: str = Field(..., min_length=2, max_length=80, description="Agent handle (e.g. @architect)")
    depends_on: List[str] = Field(default_factory=list, description="Prerequisite card IDs that must be DONE")
    priority: CardPriorityEnum = Field(default=CardPriorityEnum.MEDIUM, description="Urgency level")
    initial_lane: Optional[KanbanLaneEnum] = Field(default=None, description="Optional override initial lane")


class TransitionCardRequestDTO(BaseModel):
    """Payload to transition a card across swimlane columns."""

    target_lane: KanbanLaneEnum = Field(..., description="Destination swimlane column")
    actor: str = Field(default="human", description="Actor triggering transition (human | system | agent)")


class TransitionCardResponseDTO(BaseModel):
    """Response returned upon card state transition, including auto-unblocked cards."""

    card: KanbanCardDTO = Field(..., description="Updated card state")
    unlocked_cards: List[str] = Field(default_factory=list, description="Downstream card IDs auto-unblocked to TODO")


class MountArtifactRequestDTO(BaseModel):
    """Payload to mount an artifact to a card."""

    name: str = Field(..., min_length=1, max_length=120, description="Artifact title")
    artifact_type: str = Field(default="file", description="Artifact category (diff, file, report, test)")
    file_path: Optional[str] = Field(default=None, description="Path within workspace or card sandbox")
    content_preview: Optional[str] = Field(default=None, description="Snippet or diff text")


class HumanOverrideRequestDTO(BaseModel):
    """Payload for human-in-the-loop drag-and-drop, priority re-weighting, or agent reassignment."""

    new_agent: Optional[str] = Field(default=None, description="New specialist agent handle")
    new_priority: Optional[CardPriorityEnum] = Field(default=None, description="New priority level")
    new_lane: Optional[KanbanLaneEnum] = Field(default=None, description="Drag destination lane")


class DecomposeGoalRequestDTO(BaseModel):
    """Payload for Boss Agent (Orchestrator) automated decomposition into sequenced DAG cards."""

    goal: str = Field(..., min_length=3, description="High-level project mission to decompose")
    specialist_roster: Optional[List[str]] = Field(default=None, description="List of available specialist handles")


class DecomposeGoalResponseDTO(BaseModel):
    """Response returned upon automated goal decomposition."""

    board_id: str = Field(..., description="Target board ID")
    created_cards: List[KanbanCardDTO] = Field(default_factory=list, description="Sequenced DAG task cards created")
