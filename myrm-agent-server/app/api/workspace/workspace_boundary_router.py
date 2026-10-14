"""[INPUT]
ProjectSwitchHandshakeRequest from app.services.workspace.boundary.boundary_types
[OUTPUT]
FastAPI router for workspace boundary 3-currents inspection and switch handshake.
[POS]
app/api/workspace/workspace_boundary_router.py
"""

from typing import Optional
from fastapi import APIRouter, Query

from app.services.workspace.boundary.boundary_types import (
    MultiRepoWorktreeEntry,
    ProjectSwitchHandshakeRequest,
    ProjectSwitchHandshakeResponse,
    ThreeCurrentsBoundary,
)
from app.services.workspace.boundary.workspace_boundary_service import (
    WorkspaceBoundaryInspectorService,
)

router = APIRouter(prefix="/boundary", tags=["workspace-boundary"])

_inspector_service = WorkspaceBoundaryInspectorService()


@router.get("/current", response_model=ThreeCurrentsBoundary)
def get_current_boundary(
    session_id: str = Query("default-session", description="Active session ID"),
    project_id: str = Query("default-project", description="Active project ID"),
    project_name: Optional[str] = Query(None, description="Optional project display name"),
    session_goal: Optional[str] = Query(None, description="Optional active session goal"),
    cwd: Optional[str] = Query(None, description="Optional directory path to inspect"),
) -> ThreeCurrentsBoundary:
    """Inspect and return active 3-currents execution boundary (Session Goal, CWD/Branch, Host)."""
    return _inspector_service.inspect_three_currents(
        session_id=session_id,
        project_id=project_id,
        project_name=project_name,
        session_goal=session_goal,
        custom_cwd=cwd,
    )


@router.post("/handshake", response_model=ProjectSwitchHandshakeResponse)
def handshake_project_switch(
    request: ProjectSwitchHandshakeRequest,
) -> ProjectSwitchHandshakeResponse:
    """Execute zero-risk read-only probe for switching workspace project."""
    return _inspector_service.handshake_project_switch(request)


@router.get("/worktrees", response_model=list[MultiRepoWorktreeEntry])
def list_workspace_worktrees(
    cwd: Optional[str] = Query(None, description="Workspace repository directory"),
) -> list[MultiRepoWorktreeEntry]:
    """List active repositories and Git worktree branches for the workspace."""
    return _inspector_service.list_worktrees(target_dir=cwd)
