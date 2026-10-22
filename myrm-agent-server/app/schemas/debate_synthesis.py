"""[INPUT] None.
[OUTPUT] Pydantic models and request/response DTOs for Hierarchical Leader-Worker Debate & Synthesis Pattern.
[POS] HTTP schema validation layer for debate synthesis endpoints.
"""

from __future__ import annotations

import time

from myrm_agent_harness.agent.sub_agents.debate.synthesis_pattern.types import (
    SynthesisPhase,
    SynthesisRole,
)
from pydantic import BaseModel, Field


class SynthesisParticipantDTO(BaseModel):
    """Participant profile in the hierarchical synthesis panel."""

    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Display name of the agent")
    role: SynthesisRole = Field(..., description="Specialist role in consulting pattern")
    model: str | None = Field(default=None, description="Underlying model identifier")


class SynthesisSubtaskDTO(BaseModel):
    """Subtask derived by Leader with topological dependency metadata."""

    task_id: str = Field(..., description="Subtask identifier")
    title: str = Field(..., description="Subtask title")
    assigned_role: SynthesisRole = Field(..., description="Assigned specialist role")
    assigned_agent_id: str = Field(..., description="Assigned agent ID")
    description: str = Field(..., description="Detailed requirements")
    depends_on: list[str] = Field(default_factory=list, description="IDs of prerequisite tasks")
    status: str = Field(default="todo", description="Execution status")
    output_summary: str | None = Field(default=None, description="Result output summary")


class CandidateProposalDTO(BaseModel):
    """Candidate solution proposal drafted by an analyst or auditor."""

    proposal_id: str = Field(..., description="Unique proposal identifier")
    title: str = Field(..., description="Proposal title")
    author_role: SynthesisRole = Field(..., description="Role of the authoring agent")
    author_agent_id: str = Field(..., description="Agent ID who drafted proposal")
    summary: str = Field(..., description="Executive summary of candidate solution")
    pros: list[str] = Field(default_factory=list, description="Key advantages and strengths")
    cons: list[str] = Field(default_factory=list, description="Known risks and trade-offs")
    dimension_scores: dict[str, float] = Field(default_factory=dict, description="Normalized scores (0-1) across dimensions")
    is_recommended: bool = Field(default=False, description="Whether selected as final recommendation")


class TradeoffMatrixDTO(BaseModel):
    """Multidimensional decision trade-off matrix synthesized by the Leader."""

    matrix_id: str = Field(..., description="Matrix unique identifier")
    workflow_id: str = Field(..., description="Parent workflow ID")
    dimensions: list[str] = Field(default_factory=list, description="Evaluated comparison dimensions")
    dimension_weights: dict[str, float] = Field(default_factory=dict, description="Normalized dimension weights")
    proposals: list[CandidateProposalDTO] = Field(default_factory=list, description="Evaluated candidate proposals")
    winner_proposal_id: str | None = Field(default=None, description="Proposal ID recommended as optimal")
    recommendation_rationale: str = Field(..., description="Leader justification and trade-off summary")
    created_at: float = Field(default_factory=time.time, description="Synthesis timestamp")


class SynthesisWorkflowResponse(BaseModel):
    """State payload for a hierarchical debate & synthesis session."""

    workflow_id: str = Field(..., description="Workflow unique identifier")
    chat_id: str = Field(..., description="Chat conversation ID")
    topic: str = Field(..., description="Core consultation problem or topic")
    phase: SynthesisPhase = Field(..., description="Current lifecycle phase")
    participants: list[SynthesisParticipantDTO] = Field(default_factory=list, description="Panel participants")
    subtasks: list[SynthesisSubtaskDTO] = Field(default_factory=list, description="Derived subtasks DAG")
    proposals: list[CandidateProposalDTO] = Field(default_factory=list, description="Submitted proposals")
    matrix: TradeoffMatrixDTO | None = Field(default=None, description="Synthesized decision trade-off matrix")
    round_index: int = Field(default=1, description="Current debate round number")
    max_rounds: int = Field(default=2, description="Maximum allowed debate rounds")
    created_at: float = Field(default_factory=time.time, description="Creation timestamp")
    updated_at: float = Field(default_factory=time.time, description="Last updated timestamp")


class CreateSynthesisWorkflowRequest(BaseModel):
    """Payload to launch a hierarchical debate synthesis session."""

    workflow_id: str | None = Field(default=None, description="Optional custom workflow ID")
    topic: str = Field(..., description="Consultation problem statement")
    leader_id: str = Field(default="agent-leader", description="Agent ID of Leader Coordinator")
    researcher_id: str = Field(default="agent-researcher", description="Agent ID of Research Analyst")
    auditor_id: str = Field(default="agent-auditor", description="Agent ID of Feasibility Auditor")
    max_rounds: int = Field(default=2, ge=1, le=5, description="Maximum debate rounds before forced convergence")


class AutoDecomposeRequest(BaseModel):
    """Payload for Leader to derive subtask DAG."""

    leader_agent_id: str = Field(..., description="Agent ID of the requesting leader")


class SubmitProposalRequest(BaseModel):
    """Payload to submit a candidate proposal."""

    proposal_id: str | None = Field(default=None, description="Optional proposal ID")
    title: str = Field(..., description="Proposal title")
    author_role: SynthesisRole = Field(..., description="Author role (research_analyst or feasibility_auditor)")
    author_agent_id: str = Field(..., description="Author agent ID")
    summary: str = Field(..., description="Proposal summary")
    pros: list[str] = Field(default_factory=list, description="Strengths and advantages")
    cons: list[str] = Field(default_factory=list, description="Weaknesses and drawbacks")
    dimension_scores: dict[str, float] = Field(default_factory=dict, description="Scores between 0.0 and 1.0")


class SynthesizeMatrixRequest(BaseModel):
    """Payload to finalize decision trade-off matrix."""

    custom_weights: dict[str, float] | None = Field(default=None, description="Optional custom dimension weights")
    custom_rationale: str | None = Field(default=None, description="Optional Leader customized rationale")
