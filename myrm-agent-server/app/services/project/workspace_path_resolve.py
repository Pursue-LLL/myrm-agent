"""[INPUT]
- myrm_agent_harness.agent.security.path_security::is_dangerous_path

[OUTPUT]
- normalize_project_workspace_path: validate and canonicalize user-supplied bind paths
- WorkspacePathValidationError: raised when path is rejected

[POS]
Project workspace bind path normalization. Used by Project API before persisting
workspace_path so GUI folder picks and manual paths share one validation path.
"""

from __future__ import annotations

import os
from pathlib import Path


class WorkspacePathValidationError(ValueError):
    """Raised when a project workspace_path fails validation."""


def normalize_project_workspace_path(raw: str) -> str:
    """Expand, resolve, and validate a project workspace bind path.

    Empty input clears the bind. Non-empty paths must be absolute after expansion,
    must not match dangerous-path rules, and are stored as resolved strings.
    """
    trimmed = raw.strip()
    if not trimmed:
        return ""

    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    expanded = os.path.expanduser(trimmed)
    candidate = Path(expanded)
    if not candidate.is_absolute():
        raise WorkspacePathValidationError("workspace_path must be an absolute path")

    resolved = str(candidate.resolve())
    if is_dangerous_path(resolved):
        raise WorkspacePathValidationError(f"Access denied for path: {trimmed}")

    return resolved
