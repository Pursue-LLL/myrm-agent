"""Schemas and DTOs for Task Execution Triad State Trajectory and Anti-Loop Blackbox.

[INPUT]
- External: pydantic, datetime

[OUTPUT]
- RecordMilestoneRequestDTO: Payload for logging a verified milestone.
- RecordFailedAttemptRequestDTO: Payload for logging a dead-end execution attempt.
- RecordUserSteeringRequestDTO: Payload for capturing in-flight user instructions.
- CheckActionRequestDTO: Request to verify whether an action triggers dead-ends.
- CheckActionResponseDTO: Decision and matched prohibited rule.
- AntiLoopSnapshotResponseDTO: Lightweight pre-prompt snapshot payload.
- TaskTrajectoryBlackboxResponseDTO: Complete blackbox state trajectory for auditing or handoff.

[POS]
Server data transfer objects for long-horizon task triad memory.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class MilestoneItemDTO(BaseModel):
    """Verified milestone item in trajectory."""

    milestone_id: str
    step_index: int
    title: str
    description: str = ""
    verified_output_summary: str
    artifacts_produced: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FailedAttemptItemDTO(BaseModel):
    """Dead-end failure item with anti-loop rule."""

    attempt_id: str
    step_index: int
    action_attempted: str
    error_type: str
    error_summary: str
    dead_end_pattern: str
    prohibited_rule: str
    lessons_learned: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserSteeringItemDTO(BaseModel):
    """In-flight user steering constraint."""

    steering_id: str
    turn_index: int
    instruction_raw: str
    distilled_constraint: str
    scope: str = "global"
    is_active: bool = True
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecordMilestoneRequestDTO(BaseModel):
    """Payload to log a completed milestone."""

    task_id: str = Field(description="Task identifier")
    session_id: str = Field(description="Session identifier")
    initial_goal: str = Field(default="Long-horizon agent execution", description="Initial task goal")
    step_index: int = Field(ge=0, description="Step index")
    title: str = Field(description="Milestone title")
    verified_output_summary: str = Field(description="Verification proof or outcome")
    description: str = Field(default="", description="Detailed description")
    artifacts_produced: list[str] = Field(default_factory=list, description="Artifact paths")


class RecordFailedAttemptRequestDTO(BaseModel):
    """Payload to log a dead-end failed attempt."""

    task_id: str = Field(description="Task identifier")
    session_id: str = Field(description="Session identifier")
    initial_goal: str = Field(default="Long-horizon agent execution", description="Initial task goal")
    step_index: int = Field(ge=0, description="Step index")
    action_attempted: str = Field(description="Command or tool call executed")
    error_type: str = Field(description="Error classification")
    error_summary: str = Field(description="Reason of failure")
    dead_end_pattern: str = Field(description="Matching pattern for detection")
    prohibited_rule: str = Field(description="Actionable prohibition rule")
    lessons_learned: str = Field(default="", description="Lessons learned")


class RecordUserSteeringRequestDTO(BaseModel):
    """Payload to record in-flight user steering instruction."""

    task_id: str = Field(description="Task identifier")
    session_id: str = Field(description="Session identifier")
    initial_goal: str = Field(default="Long-horizon agent execution", description="Initial task goal")
    turn_index: int = Field(ge=0, description="Dialogue turn index")
    instruction_raw: str = Field(description="Raw user message")
    distilled_constraint: str = Field(description="Distilled constraint text")
    scope: str = Field(default="global", description="Constraint scope")


class CheckActionRequestDTO(BaseModel):
    """Payload to query whether an action is prohibited."""

    task_id: str = Field(description="Task identifier")
    action_text: str = Field(description="Intended action command or tool invocation")


class CheckActionResponseDTO(BaseModel):
    """Response verifying whether action triggers dead-ends."""

    is_prohibited: bool = Field(description="True if action is blocked by a dead-end rule")
    matched_rule: str | None = Field(default=None, description="Prohibited rule if blocked")
    error_summary: str | None = Field(default=None, description="Past failure reason if blocked")
    matched_pattern: str | None = Field(default=None, description="Dead-end pattern matched")


class AntiLoopSnapshotResponseDTO(BaseModel):
    """Pre-prompt snapshot payload for model injection."""

    task_id: str
    snapshot_token_estimate: int
    dead_end_rules_injected: list[str] = Field(default_factory=list)
    active_user_steerings_injected: list[str] = Field(default_factory=list)
    latest_milestone_title: str | None = None
    formatted_prompt_block: str


class TaskTrajectoryBlackboxResponseDTO(BaseModel):
    """Full task trajectory blackbox details."""

    task_id: str
    session_id: str
    initial_goal: str
    status: str
    version: int
    milestones: list[MilestoneItemDTO] = Field(default_factory=list)
    failed_attempts: list[FailedAttemptItemDTO] = Field(default_factory=list)
    user_steerings: list[UserSteeringItemDTO] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
