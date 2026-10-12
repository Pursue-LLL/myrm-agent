"""
[INPUT]
- Pydantic v2 BaseModels for Project-Centric Session Map and Agent State Cockpit View.
- Session and Project domain entities.

[OUTPUT]
- SessionNodeModel: Representation of a chat session/agent node in the 2D topology.
- ProjectClusterModel: Project container grouping sessions by repository and working path.
- FleetCockpitSummary: Aggregate metrics for hundreds of concurrent agents in fleet.
- SessionSearchRequest & SessionSearchResponse: Multi-attribute and full-text session retrieval.

[POS]
Pydantic contracts for Project-Centric Session Map and Fleet Cockpit View.
Zero `Any` types. File length < 140 lines.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

AgentState = Literal["working", "ready", "waiting_input", "idle", "error"]


class SessionNodeModel(BaseModel):
    id: str = Field(..., description="Unique session ID")
    title: str = Field(..., description="Session title or objective summary")
    project_id: Optional[str] = Field(None, description="Bound project identifier")
    agent_id: Optional[str] = Field(None, description="Bound agent ID")
    agent_name: str = Field(default="Myrm-Core", description="Display name of assigned agent")
    state: AgentState = Field(default="ready", description="Current runtime state of the agent")
    current_task: Optional[str] = Field(None, description="Active task objective description")
    tokens_used: int = Field(default=0, description="Total token consumption in this session")
    last_active_at: str = Field(..., description="ISO timestamp of last activity")
    tags: List[str] = Field(default_factory=list, description="Categorical or workflow tags")
    workspace_dir: Optional[str] = Field(None, description="Isolated working directory or git worktree")
    match_highlights: Optional[List[str]] = Field(None, description="Matched search snippet highlights")


class ProjectClusterModel(BaseModel):
    id: str = Field(..., description="Unique project ID")
    name: str = Field(..., description="Project name")
    description: str = Field(default="", description="Project objective description")
    color: str = Field(default="#6366f1", description="Theme accent color hex")
    workspace_path: Optional[str] = Field(None, description="Local root workspace path")
    git_repo_url: Optional[str] = Field(None, description="Bound Git repository URL or remote")
    sessions: List[SessionNodeModel] = Field(default_factory=list, description="Child session nodes")
    active_agent_count: int = Field(default=0, description="Count of agents currently working or ready")
    total_tokens: int = Field(default=0, description="Aggregate token consumption across all sessions")


class FleetCockpitSummary(BaseModel):
    total_projects: int = Field(default=0, description="Total managed projects")
    total_sessions: int = Field(default=0, description="Total session nodes in map")
    total_agents: int = Field(default=0, description="Total agents across all nodes")
    working_agents: int = Field(default=0, description="Count of agents executing tasks")
    ready_agents: int = Field(default=0, description="Count of agents standby ready")
    waiting_input_agents: int = Field(default=0, description="Count of agents awaiting user input")
    error_agents: int = Field(default=0, description="Count of agents in error/blocked state")
    total_tokens_consumed: int = Field(default=0, description="Global aggregate token consumption")
    top_active_sessions: List[SessionNodeModel] = Field(default_factory=list, description="Top active session nodes")


class SessionSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search keyword or semantic query")
    project_id: Optional[str] = Field(None, description="Optional filter by project ID")
    state: Optional[AgentState] = Field(None, description="Optional filter by agent state")


class SessionSearchHit(BaseModel):
    session: SessionNodeModel
    project_name: str
    relevance_score: float
    matched_snippet: str


class SessionSearchResponse(BaseModel):
    query: str
    total_hits: int
    hits: List[SessionSearchHit]
