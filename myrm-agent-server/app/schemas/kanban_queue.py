"""Pydantic schemas for Persistent Kanban Job Queue and Massive Parallel Dogfooding Runner."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class KanbanJobStatusEnum(str, Enum):
    """5-State lifecycle for persistent kanban jobs + blocked state."""

    TRIAGE = "triage"
    TODO = "todo"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    BLOCKED = "blocked"


class SwarmTopologyStageEnum(str, Enum):
    """Swarm 4-stage topology."""

    PLANNING_ROOT = "planning_root"
    PARALLEL_SPECIALIST = "parallel_specialist"
    VERIFIER_GATE = "verifier_gate"
    SYNTHESIZER = "synthesizer"


class JobPriorityEnum(str, Enum):
    """Priority levels for kanban jobs."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class KanbanCommentDTO(BaseModel):
    author: str
    content: str
    timestamp: float
    is_blackboard: bool = False


class BlackboardEntryDTO(BaseModel):
    entry_id: str
    job_id: str
    stage: SwarmTopologyStageEnum
    author: str
    payload: Dict[str, str] = Field(default_factory=dict)
    created_at: float


class KanbanJobDTO(BaseModel):
    job_id: str
    title: str
    goal: str
    approach: str = ""
    acceptance_criteria: List[str] = Field(default_factory=list)
    status: KanbanJobStatusEnum
    priority: JobPriorityEnum = JobPriorityEnum.NORMAL
    stage: SwarmTopologyStageEnum = SwarmTopologyStageEnum.PARALLEL_SPECIALIST
    assignee: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None
    worktree_path: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    comments: List[KanbanCommentDTO] = Field(default_factory=list)
    result_summary: Optional[str] = None
    result_metadata: Dict[str, str] = Field(default_factory=dict)
    failure_count: int = 0
    goal_mode: bool = False
    goal_max_turns: int = 15
    last_heartbeat_timestamp: float
    created_at: float
    updated_at: float


class CreateKanbanJobRequest(BaseModel):
    title: str
    goal: str
    approach: str = ""
    acceptance_criteria: List[str] = Field(default_factory=list)
    priority: JobPriorityEnum = JobPriorityEnum.NORMAL
    stage: SwarmTopologyStageEnum = SwarmTopologyStageEnum.PARALLEL_SPECIALIST
    assignee: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    goal_mode: bool = False
    goal_max_turns: int = 15


class ClaimKanbanJobRequest(BaseModel):
    assignee: str


class CompleteKanbanJobRequest(BaseModel):
    summary: str
    metadata: Dict[str, str] = Field(default_factory=dict)


class BlockKanbanJobRequest(BaseModel):
    reason: str


class AddCommentRequest(BaseModel):
    author: str
    content: str


class LinkDependencyRequest(BaseModel):
    from_job_id: str
    to_job_id: str


class SpecifyPromptRequest(BaseModel):
    prompt: str


class SpecifyPromptResponse(BaseModel):
    title: str
    goal: str
    approach: str
    acceptance_criteria: List[str] = Field(default_factory=list)


class SubtaskSpecDTO(BaseModel):
    title: str
    goal: str
    approach: str = ""
    assignee: Optional[str] = None


class DecomposeJobRequest(BaseModel):
    subtasks: List[SubtaskSpecDTO] = Field(default_factory=list)


class ToggleCircuitBreakerRequest(BaseModel):
    enabled: bool


class DispatchWaveRequest(BaseModel):
    max_parallel: int = 12
    distribution_strategy: str = "round_robin"


class DispatchWaveResponseDTO(BaseModel):
    dispatched: int
    running: int
    completed: int
    active_workers: int


class BatchRunnerStatusDTO(BaseModel):
    total_jobs: int
    done_jobs: int
    ready_jobs: int
    running_jobs: int
    blocked_jobs: int
    resume_available: bool
    trajectories_collected: int
