"""[POS]: app/schemas/decisions.py
[INPUT]: API request payloads for architecture decision staging, confirmation, and recall.
[OUTPUT]: Pydantic v2 schemas for HTTP endpoints governing decisions as state and lineage.
"""

from pydantic import BaseModel, Field


class StageDecisionCandidateRequest(BaseModel):
    """Payload to stage a proposed architectural decision candidate."""

    session_id: str = Field(description="Conversation session ID")
    title: str = Field(description="Succinct technical topic or decision headline")
    text: str = Field(description="Concrete decision statement and chosen specification")
    rationale: str = Field(default="", description="Architectural tradeoffs and rationale")
    supersedes_id: str | None = Field(default=None, description="Prior decision ID to supersede")
    project_key: str = Field(default="default", description="Workspace or project key")


class ConfirmCandidateRequest(BaseModel):
    """Payload to approve a staged decision candidate."""

    candidate_id: str = Field(description="ID of the candidate to approve")


class RejectCandidateRequest(BaseModel):
    """Payload to reject a staged decision candidate."""

    candidate_id: str = Field(description="ID of the candidate to reject")


class RecordDecisionDirectRequest(BaseModel):
    """Payload to directly record an active architecture decision."""

    title: str = Field(description="Succinct technical topic or decision headline")
    text: str = Field(description="Concrete decision statement and chosen specification")
    rationale: str = Field(default="", description="Architectural tradeoffs and rationale")
    supersedes_id: str | None = Field(default=None, description="Prior decision ID to supersede")
    scope: str = Field(default="project", description="Decision scope")
    project_key: str = Field(default="default", description="Workspace or project key")
    source_event: str | None = Field(default=None, description="Event trace anchor")


class DecisionPrioritySearchRequest(BaseModel):
    """Payload to query prioritized structured decisions with MMR and prompt synthesis."""

    query: str = Field(description="Search or natural language question")
    project_key: str = Field(default="default", description="Project namespace")
    limit: int = Field(default=5, ge=1, le=50, description="Max priority hits to return")


class DecisionResponse(BaseModel):
    """Serialized representation of an EngineeringDecisionRecord."""

    id: str
    title: str
    text: str
    rationale: str
    status: str
    supersedes_id: str | None = None
    superseded_by: str | None = None
    scope: str
    project_key: str
    source_event: str | None = None
    created_at: str
    updated_at: str


class CandidateResponse(BaseModel):
    """Serialized representation of a PendingDecisionCandidate."""

    id: str
    session_id: str
    title: str
    text: str
    rationale: str
    supersedes_id: str | None = None
    status: str
    project_key: str
    created_at: str
    updated_at: str


class DecisionRecallHitResponse(BaseModel):
    """Prioritized recall hit item."""

    decision_id: str
    title: str
    text: str
    rationale: str
    status: str
    supersedes_id: str | None = None
    superseded_by: str | None = None
    score: float
    is_priority: bool
    formatted_line: str
    source_event: str | None = None
    created_at: str


class DecisionPrioritySearchResponse(BaseModel):
    """Response containing prioritized hits and synthesized markdown prompt block."""

    hits: list[DecisionRecallHitResponse]
    prompt_block: str
