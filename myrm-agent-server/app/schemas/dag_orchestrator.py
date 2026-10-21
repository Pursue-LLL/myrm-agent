"""Pydantic schemas for DAG Visual Orchestrator with Cold Resume and Bidirectional Feedback."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DagNodeStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED_LOOPBACK = "rejected_loopback"


class DagRoleEnum(str, Enum):
    ANALYST = "analyst"
    ARCHITECT = "architect"
    CODER = "coder"
    TESTER = "tester"
    RELEASE_MANAGER = "release_manager"


class DagNodeDTO(BaseModel):
    node_id: str
    role: DagRoleEnum
    title: str
    instruction: str
    depends_on: List[str] = Field(default_factory=list)
    status: DagNodeStatusEnum = DagNodeStatusEnum.PENDING
    output_artifact: Optional[str] = None
    rejection_feedback: Optional[str] = None
    execution_time_ms: int = 0


class DagPlanRequest(BaseModel):
    goal: str
    dag_id: Optional[str] = None


class DagPlanResponse(BaseModel):
    dag_id: str
    goal: str
    nodes: Dict[str, DagNodeDTO]
    topological_order: List[str]
    ready_node_ids: List[str]


class DagExecuteStepRequest(BaseModel):
    node_id: str


class DagColdResumeResponse(BaseModel):
    dag_id: str
    nodes: Dict[str, DagNodeDTO]
    ready_node_ids: List[str]
    completed_count: int


class DagRejectLoopbackRequest(BaseModel):
    target_node_id: str
    rejection_feedback: str


class DagRejectLoopbackResponse(BaseModel):
    target_node_id: str
    affected_node_ids: List[str]
    nodes: Dict[str, DagNodeDTO]
    next_ready_node_ids: List[str]


class DagStatusResponse(BaseModel):
    dag_id: str
    goal: str
    nodes: Dict[str, DagNodeDTO]
    ready_node_ids: List[str]
    is_completed: bool
