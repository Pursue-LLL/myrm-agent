"""
[POS] app/schemas/workflow_trace.py
[INPUT] pydantic
[OUTPUT] WorkflowStage, WorkflowNodeStatus, FourDimValidationScore, WorkflowNodeSnapshot, WorkflowTraceResponse, ReplayFromNodeRequest, ReplayFromNodeResponse
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

WorkflowStage = Literal["intake", "planning", "dispatch", "execution_validation", "closure"]

WorkflowNodeStatus = Literal["pending", "running", "completed", "failed", "retrying", "replaying"]


class FourDimValidationScore(BaseModel):
    """Four-dimensional verification scorecard for single workflow execution steps."""

    model_config = ConfigDict(extra="forbid")

    completeness: float = Field(..., ge=0.0, le=1.0, description="Completeness of sub-task outputs")
    accuracy: float = Field(..., ge=0.0, le=1.0, description="Factuality and accuracy score")
    compliance: float = Field(..., ge=0.0, le=1.0, description="Safety and policy compliance")
    relevance: float = Field(..., ge=0.0, le=1.0, description="Contextual prompt relevance")
    composite_score: float = Field(..., ge=0.0, le=1.0, description="Weighted composite audit score")


class WorkflowNodeSnapshot(BaseModel):
    """Holographic snapshot of a single node in the multi-step execution DAG."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, description="Unique node step identifier")
    step_number: int = Field(..., ge=1, description="Sequential index of the node")
    title: str = Field(..., min_length=1, description="Human-readable title of this step")
    stage: WorkflowStage = Field(..., description="Belonging stage in the 5-phase lifecycle")
    status: WorkflowNodeStatus = Field(..., description="Current execution state")
    input_payload: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict, description="In-place parameter inputs fed to this step"
    )
    output_payload: dict[str, str | int | float | bool | list[str]] | None = Field(
        default=None, description="Produced intermediate output payload"
    )
    prompt_excerpt: str | None = Field(
        default=None, description="Independent prompt instruction sent to LLM for this node"
    )
    tools_called: list[str] = Field(
        default_factory=list, description="List of tool names invoked during step execution"
    )
    tokens_consumed: int = Field(default=0, ge=0, description="Tokens consumed during step execution")
    validation_scores: FourDimValidationScore | None = Field(
        default=None, description="Four-dimensional audit scorecard"
    )
    duration_ms: float = Field(default=0.0, ge=0.0, description="Execution duration in milliseconds")
    created_at: str = Field(..., description="Timestamp of step creation")
    identity_hash: str = Field(..., description="Fingerprint hash supporting SQLite checkpoint replay")


class WorkflowTraceResponse(BaseModel):
    """Full execution trajectory payload for the multi-step workflow visualizer."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1, description="Unique workflow run identifier")
    task_id: str = Field(..., min_length=1, description="Associated task identifier")
    title: str = Field(..., min_length=1, description="Workflow goal or title")
    current_stage: WorkflowStage = Field(..., description="Active phase in the 5-stage lifecycle")
    nodes: list[WorkflowNodeSnapshot] = Field(
        default_factory=list, description="Ordered snapshots of all workflow nodes"
    )
    total_tokens: int = Field(default=0, ge=0, description="Cumulative tokens across all steps")
    total_duration_ms: float = Field(default=0.0, ge=0.0, description="Total execution duration in ms")


class ReplayFromNodeRequest(BaseModel):
    """Request payload to initiate breakpoint replay from a selected node with modified inputs."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1, description="Target workflow identifier")
    node_id: str = Field(..., min_length=1, description="Target breakpoint node to replay from")
    override_inputs: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict, description="User-modified parameter overrides"
    )
    steer_prompt: str | None = Field(
        default=None, description="Optional steer prompt or guidance for the replayed step"
    )


class ReplayFromNodeResponse(BaseModel):
    """Outcome of breakpoint replay execution leveraging cached parent snapshots."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., description="Target workflow identifier")
    replayed_from_node_id: str = Field(..., description="Breakpoint node re-executed")
    status: Literal["resumed", "completed", "failed"] = Field(..., description="Replay status")
    message: str = Field(..., description="Diagnostic summary of the breakpoint replay")
    replayed_nodes: list[WorkflowNodeSnapshot] = Field(
        default_factory=list, description="Refreshed node snapshots after breakpoint re-execution"
    )
