"""The directories this run may reach beyond its workspace, as the executor reaches them.

[INPUT]
- core.context_vars::reachable_access_roots (POS: the policy's roots plus what the person granted, as the permission engine also judges)
- core.security.path::is_within_boundary (POS: symlink-safe containment test)

[OUTPUT]
- granted_root_containing: the grant that holds a path
- refuse_write_into_readonly_grant: PermissionError for a write into a directory granted read-only

[POS]
The executor's boundary is the workspace plus the roots the policy names and the person granted, so a path the
engine lets through is a path the executor reaches; a read-only grant never lets a write through.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.core.context_vars import reachable_access_roots
from myrm_agent_harness.core.security.path import is_within_boundary

if TYPE_CHECKING:
    from myrm_agent_harness.core.security.types import AccessRoot


def granted_root_containing(resolved: str | Path) -> AccessRoot | None:
    """The most specific directory that holds ``resolved`` (a writable one when two are as specific), or None."""
    holding = [root for root in reachable_access_roots() if is_within_boundary(resolved, root.path)]
    return max(holding, key=lambda root: (len(root.path), root.writable), default=None)


def refuse_write_into_readonly_grant(resolved: str | Path, workspace: str | Path) -> None:
    """Refuse a write that lands in a directory granted read-only; the workspace itself is always writable."""
    if is_within_boundary(resolved, workspace):
        return
    root = granted_root_containing(resolved)
    if root is not None and not root.writable:
        raise PermissionError(f"Write denied: '{resolved}' is inside '{root.path}', which was granted read-only.")
