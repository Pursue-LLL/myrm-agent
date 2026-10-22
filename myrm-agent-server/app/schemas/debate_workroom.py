"""[INPUT] None.
[OUTPUT] Pydantic models and request/response DTOs for Multi-Agent Debate Workroom & Kanban Integration.
[POS] HTTP schema validation layer for multi-agent workroom debate endpoints.
"""

from __future__ import annotations

import time
from typing import Literal

from myrm_agent_harness.agent.sub_agents.debate.types import (
    DebatePhase,
    DebateRole,
    DebateSubtaskStatus,
)
from pydantic import BaseModel, Field


class DebateParticipantDTO(BaseModel):
    """Profile of an agent participant in the workroom."""

    agent_id: str = Field(..., description="Unique ID of the agent")
    name: str = Field(..., description="Display name of the agent")
    role: DebateRole = Field(..., description="Specialist role in debate")
    model: str | None = Field(default=None, description="Model identifier used by this agent")


class DebateSubtaskDTO(BaseModel):
    """Actionable subtask derived by the Leader."""

    task_id: str = Field(..., description="Subtask identifier")
    title: str = Field(..., description="Subtask title")
    description: str = Field(..., description="Detailed requirements")
    assigned_agent_id: str = Field(..., description="Agent assigned to this subtask")
    assigned_role: DebateRole = Field(..., description="Specialist role assigned")
    status: DebateSubtaskStatus = Field(default=DebateSubtaskStatus.TODO, description="Execution status")
    kanban_task_id: str | None = Field(default=None, description="Linked Kanban task card ID")


class DebateTurnDTO(BaseModel):
    """Single argument, cross-examination, or evidence submission."""

    turn_id: str = Field(..., description="Turn unique identifier")
    speaker_id: str = Field(..., description="Agent ID who spoke")
    speaker_name: str = Field(..., description="Display name of speaker")
    role: DebateRole = Field(..., description="Role of the speaker")
    phase: DebatePhase = Field(..., description="Phase during which turn took place")
    round_index: int = Field(..., description="Debate round number")
    thesis: str = Field(..., description="Primary thesis or critique")
    counter_points: list[str] = Field(default_factory=list, description="Direct counter-arguments")
    evidence: list[str] = Field(default_factory=list, description="Empirical evidence or citations")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Speaker confidence score (0-1)")
    kanban_task_id: str | None = Field(default=None, description="Associated Kanban task if applicable")
    created_at: float = Field(default_factory=time.time, description="Timestamp of turn")


class CreateDebateRoomRequest(BaseModel):
    """Payload to initialize a project workroom debate."""

    room_id: str | None = Field(default=None, description="Optional custom room ID")
    topic: str = Field(..., min_length=1, description="Root task topic or problem statement")
    leader_agent_id: str = Field(..., description="Agent designated as the debate leader")
    participants: list[DebateParticipantDTO] = Field(default_factory=list, description="Debate members")
    max_rounds: int = Field(default=3, ge=1, le=10, description="Max debate rounds before forced convergence")
    kanban_board_id: str | None = Field(default=None, description="Optional target Kanban board ID")


class DecomposeTaskRequest(BaseModel):
    """Leader subtask decomposition submission."""

    subtasks: list[DebateSubtaskDTO] = Field(..., min_length=1, description="Decomposed subtasks list")


class PostArgumentRequest(BaseModel):
    """Post an argument or critique into the debate stream."""

    speaker_id: str = Field(..., description="Agent ID posting the argument")
    thesis: str = Field(..., min_length=1, description="Primary argument or critique thesis")
    counter_points: list[str] = Field(default_factory=list, description="Specific counter-points raised")
    evidence: list[str] = Field(default_factory=list, description="Supporting evidence or log snippets")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence level")
    kanban_task_id: str | None = Field(default=None, description="Associated Kanban task ID")


class AdvancePhaseRequest(BaseModel):
    """Explicitly step or transition the debate phase."""

    target_phase: DebatePhase | None = Field(default=None, description="Target phase to jump to")


class SynthesizeDecisionRequest(BaseModel):
    """Leader or Synthesizer final consensus declaration."""

    consensus_decision: str = Field(..., min_length=1, description="Synthesized final decision text")
    settled_subtask_ids: list[str] = Field(default_factory=list, description="Subtask IDs settled to DONE")


class SyncKanbanSubtaskRequest(BaseModel):
    """Synchronize Kanban card status with a debate subtask."""

    kanban_task_id: str = Field(..., description="Kanban task card ID")
    kanban_status: str | None = Field(default=None, description="New status string from Kanban board")


class DebateRoomResponse(BaseModel):
    """Full aggregate response for a debate room state."""

    room_id: str
    chat_id: str
    topic: str
    leader_agent_id: str
    phase: DebatePhase
    round_index: int
    max_rounds: int
    participants: list[DebateParticipantDTO]
    subtasks: list[DebateSubtaskDTO]
    turns: list[DebateTurnDTO]
    consensus_decision: str | None
    kanban_board_id: str | None
    created_at: float
    updated_at: float


class DebateRoomListResponse(BaseModel):
    """Paginated or listed debate rooms for a chat."""

    chat_id: str
    rooms: list[DebateRoomResponse]
    total: int


class OperationStatusResponse(BaseModel):
    """Generic operation status response."""

    status: Literal["ok", "deleted", "synced"]
    room_id: str
    message: str | None = None
