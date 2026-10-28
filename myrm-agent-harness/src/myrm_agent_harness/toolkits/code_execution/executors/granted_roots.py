"""The directories the user granted for this run, as the executor reaches them.

[INPUT]
- core.context_vars::session_access_roots_var (POS: the grants the permission engine also judges by)
- core.security.path::is_within_boundary (POS: symlink-safe containment test)

[OUTPUT]
- granted_root_containing: the grant that holds a path
- refuse_write_into_readonly_grant: PermissionError for a write into a directory granted read-only

[POS]
The executor's boundary is the workspace plus these grants: the user's approval of a directory is the
only thing that widens it, and a read-only grant never lets a write through.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.core.context_vars import session_access_roots_var
from myrm_agent_harness.core.security.path import is_within_boundary

if TYPE_CHECKING:
    from myrm_agent_harness.core.security.types import AccessRoot


def granted_root_containing(resolved: str | Path) -> AccessRoot | None:
    """The most specific granted directory that holds ``resolved``, or None."""
    best: AccessRoot | None = None
    for root in session_access_roots_var.get():
        if is_within_boundary(resolved, root.path) and (best is None or len(root.path) > len(best.path)):
            best = root
    return best


def refuse_write_into_readonly_grant(resolved: str | Path, workspace: str | Path) -> None:
    """Refuse a write that lands in a directory granted read-only; the workspace itself is always writable."""
    if is_within_boundary(resolved, workspace):
        return
    root = granted_root_containing(resolved)
    if root is not None and not root.writable:
        raise PermissionError(f"Write denied: '{resolved}' is inside '{root.path}', which was granted read-only.")
