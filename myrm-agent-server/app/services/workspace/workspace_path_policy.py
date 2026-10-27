"""Workspace path policy: the one gate every user- or transcript-supplied workspace path passes.

[INPUT]
- myrm_agent_harness.agent.security.path_security::is_dangerous_path, covers_dangerous_path
- app.config.settings::get_settings (POS: state_dir, the directory holding the database and every chat workspace)
- app.core.utils.errors::validation_error
- app.schemas.responses::ErrorDetail

[OUTPUT]
- WorkspacePathIssue: machine-readable rejection reasons surfaced to clients as ``ErrorDetail.issue``
- WorkspacePathValidationError: a rejected path, carrying its issue
- resolve_workspace_path: expand, canonicalize and validate a path that may become a workspace
- is_workspace_root_grantable: read-side check that an already stored workspace may still be used (same breadth rule)
- workspace_path_http_error: 400 response for a rejected path

[POS]
Binding a workspace grants the sandbox write access to the whole folder tree. A folder that is, or
contains, a credential or system root (home, a drive root, ``/``) or the application state directory
must therefore never become a workspace, whichever entry point proposed it: project create/adopt, chat
workspace PATCH, IM ``/bind`` or an imported transcript.
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

from app.core.utils.errors import StandardHTTPException, validation_error
from app.schemas.responses import ErrorDetail


class WorkspacePathIssue(StrEnum):
    """Why a path cannot be a workspace; the values are the API contract with the frontend."""

    NOT_ABSOLUTE = "not_absolute"
    DANGEROUS = "dangerous"
    TOO_BROAD = "too_broad"
    NOT_A_DIRECTORY = "not_a_directory"


class WorkspacePathValidationError(ValueError):
    """A path was rejected as a workspace."""

    def __init__(self, issue: WorkspacePathIssue, message: str) -> None:
        super().__init__(message)
        self.issue = issue


def _contains_state_dir(path: str) -> bool:
    """Whether ``path`` is the application state directory or one of its ancestors.

    Compared by file identity, so another spelling of the same folder (case, symlink) cannot slip past.
    The database sits directly in that directory; a workspace below it, such as a chat's own, is fine.
    """
    from app.config.settings import get_settings

    state_dir = Path(os.path.realpath(get_settings().database.state_dir))
    try:
        candidate = os.stat(path)
        return any(os.path.samestat(candidate, os.stat(folder)) for folder in (state_dir, *state_dir.parents))
    except OSError:
        return False


def _is_too_broad(resolved: str) -> bool:
    """Whether write access to ``resolved`` would also reach a protected location through the folder tree.

    The one breadth rule: the bind gate, the read-side net for stored workspaces and the ``workspaceUsable``
    flag all ask this, so a folder is never accepted by one of them and refused by another.
    """
    from myrm_agent_harness.agent.security.path_security import covers_dangerous_path

    return covers_dangerous_path(resolved) or _contains_state_dir(resolved)


def resolve_workspace_path(raw: str, *, require_directory: bool = False, allow_broad: bool = False) -> str:
    """Expand and canonicalize ``raw``; raise ``WorkspacePathValidationError`` when it cannot be a workspace.

    ``require_directory`` also refuses a path that does not exist yet (a path that exists but is not a
    directory is always refused). ``allow_broad`` skips the too-broad check for callers that only
    observe a folder (file-tree watching) instead of granting the sandbox write access to it.
    """
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    trimmed = raw.strip()
    expanded = os.path.expanduser(trimmed)
    if not trimmed or not os.path.isabs(expanded):
        raise WorkspacePathValidationError(WorkspacePathIssue.NOT_ABSOLUTE, "workspace_path must be an absolute path")

    resolved = os.path.realpath(expanded)
    if is_dangerous_path(resolved):
        raise WorkspacePathValidationError(WorkspacePathIssue.DANGEROUS, f"Access denied for path: {trimmed}")
    if not allow_broad and _is_too_broad(resolved):
        raise WorkspacePathValidationError(
            WorkspacePathIssue.TOO_BROAD,
            f"Path contains protected locations and is too broad to be a workspace: {trimmed}",
        )
    if (require_directory or os.path.exists(resolved)) and not os.path.isdir(resolved):
        raise WorkspacePathValidationError(
            WorkspacePathIssue.NOT_A_DIRECTORY, f"Path does not exist or is not a directory: {trimmed}"
        )
    return resolved


def is_workspace_root_grantable(path: str) -> bool:
    """Whether an already stored workspace may still be handed to the sandbox as a write root.

    A path that is or contains a protected root or the application state directory is refused, exactly as
    ``resolve_workspace_path`` refuses it as too broad, so data bound before that gate existed cannot grant
    what the gate would deny. A workspace nested inside a protected root (``/root/workspace`` in a
    container) stays usable: the gate's dangerous-path check is deliberately not repeated here.
    """
    return not _is_too_broad(path)


def workspace_path_http_error(exc: WorkspacePathValidationError, *, field: str) -> StandardHTTPException:
    """400 response whose ``details`` tell the client which request field was refused and why."""
    return validation_error(str(exc), details=[ErrorDetail(field=field, issue=exc.issue.value)])
