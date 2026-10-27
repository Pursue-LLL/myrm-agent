"""[INPUT]
- app.services.workspace.workspace_path_policy::resolve_workspace_path

[OUTPUT]
- normalize_project_workspace_path: validate and canonicalize user-supplied project bind paths

[POS]
Project workspace bind path normalization. Used by Project API before persisting
workspace_path so GUI folder picks and manual paths share one validation path; the rules
themselves live in the workspace path policy.
"""

from __future__ import annotations

from app.services.workspace.workspace_path_policy import resolve_workspace_path


def normalize_project_workspace_path(raw: str) -> str:
    """Canonicalize a project workspace bind path; empty input clears the bind.

    Raises ``WorkspacePathValidationError`` when the path cannot be a workspace.
    """
    trimmed = raw.strip()
    return resolve_workspace_path(trimmed) if trimmed else ""
