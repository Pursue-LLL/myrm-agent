"""[INPUT]
None
[OUTPUT]
Pydantic schemas for workspace execution boundary HUD and 3-currents state inspection.
[POS]
app/services/workspace/boundary/boundary_types.py
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

ExecutionHostType = Literal["local_host", "cloud_sandbox", "docker_container"]
RiskLevel = Literal["safe", "warning", "blocked"]


class ThreeCurrentsBoundary(BaseModel):
    """The 3 Currents Boundary model representing session goal, CWD/Git branch, and execution host."""

    session_id: str = Field(description="Active session identifier")
    project_id: str = Field(description="Active project identifier")
    project_name: str = Field(description="Display name of current project")
    session_goal: str = Field(default="", description="One-line delivery goal for active session")
    cwd: str = Field(description="Current absolute working directory path")
    repo_name: str = Field(description="Git repository directory name")
    git_branch: str = Field(description="Current active Git branch name")
    git_worktree: Optional[str] = Field(default=None, description="Active worktree name or path")
    git_is_clean: bool = Field(default=True, description="True if no uncommitted changes")
    git_uncommitted_changes: int = Field(default=0, description="Count of uncommitted dirty files")
    execution_host_type: ExecutionHostType = Field(description="Host execution topology")
    execution_host_label: str = Field(description="Human-readable host display label")
    execution_host_id: str = Field(description="Host or sandbox identifier")
    inspected_at: float = Field(description="Inspection timestamp (epoch seconds)")


class ProjectSwitchHandshakeRequest(BaseModel):
    """Request payload for zero-risk project switch handshake probe."""

    target_project_id: str = Field(description="Target project identifier to switch to")
    target_path: str = Field(description="Target workspace absolute path")
    current_session_id: Optional[str] = Field(default=None, description="Optional current active session")


class ProjectSwitchHandshakeResponse(BaseModel):
    """Result payload from zero-risk project switch handshake probe."""

    target_project_id: str = Field(description="Target project identifier")
    target_path: str = Field(description="Resolved target workspace directory")
    path_exists: bool = Field(description="Whether the target directory physically exists")
    is_git_repo: bool = Field(description="Whether target directory is a Git repository")
    git_branch: str = Field(default="", description="Target directory active Git branch")
    git_worktree: Optional[str] = Field(default=None, description="Target worktree identifier if any")
    git_uncommitted_changes: int = Field(default=0, description="Dirty file count in target directory")
    risk_level: RiskLevel = Field(description="Safety assessment: safe, warning, or blocked")
    warnings: list[str] = Field(default_factory=list, description="Descriptive warning messages")
    can_switch: bool = Field(description="Whether switch action is permitted")
    handshake_token: str = Field(description="HMAC verification token for valid switch execution")


class MultiRepoWorktreeEntry(BaseModel):
    """Entry describing a repository or worktree branch within the workspace project."""

    repo: str = Field(description="Repository name")
    worktree: Optional[str] = Field(default=None, description="Worktree name or tag")
    branch: str = Field(description="Git branch name")
    path: str = Field(description="Absolute file path on host")
    is_active: bool = Field(default=False, description="True if this is current working directory")
