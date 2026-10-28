"""Bridge between the roots the permission engine allows and the OS-level SandboxPolicy.

Every root passes the mount security gate before it reaches a SandboxPolicy writable or readable path.

[INPUT]
- myrm_agent_harness.core.security.types::AccessRoot (POS: Permission engine access root)
- myrm_agent_harness.core.security.path::is_within_boundary (POS: symlink-safe containment test)
- myrm_agent_harness.toolkits.code_execution.sandbox.mount_security_gate::validate_mount_spec (POS: Sandbox mount security gate)
- myrm_agent_harness.toolkits.code_execution.sandbox.protected_subpaths::discover_protected_subpaths (POS: Discovery of the git metadata kept read-only in a writable tree)
- myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types::SandboxPolicy (POS: Sandbox security policy DTO)

[OUTPUT]
- build_workspace_sandbox_policy: The one place a workspace root and the roots granted beside it become a sandbox policy
- sandbox_grant_roots: The granted roots the sandbox can honour, each passed through the mount gate
- UnsafeWorkspaceError: Raised when a workspace root cannot be granted as writable

[POS]
Layer 2.5 Policy Bridge. Converts the workspace and the granted roots into OS-level SandboxPolicy boundaries.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import replace

from myrm_agent_harness.core.security.path import is_within_boundary
from myrm_agent_harness.core.security.types import AccessRoot
from myrm_agent_harness.toolkits.code_execution.sandbox.mount_security_gate import (
    MountMode,
    MountSpec,
    validate_mount_spec,
)
from myrm_agent_harness.toolkits.code_execution.sandbox.protected_subpaths import (
    discover_protected_subpaths,
)
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import (
    SandboxPolicy,
)

logger = logging.getLogger(__name__)


class UnsafeWorkspaceError(ValueError):
    """The workspace root cannot be granted to the OS sandbox as a writable tree."""


def sandbox_grant_roots(work_dir: str, roots: Iterable[AccessRoot]) -> tuple[AccessRoot, ...]:
    """The granted roots the sandbox can honour, resolved and checked by the mount gate, each path once.

    A root inside the workspace adds nothing. A root the gate refuses (a writable one that contains a home
    directory, a system path, a device) is left out and logged, so a command neither reaches it nor is told it
    may. A path granted twice keeps its writable grant.
    """
    granted: dict[str, AccessRoot] = {}
    for root in roots:
        mode = MountMode.RW if root.writable else MountMode.RO
        result = validate_mount_spec(MountSpec(source_path=root.path, mode=mode, label=root.source))
        if not result.is_valid or result.sanitized_spec is None:
            logger.warning("Granted root left out of the sandbox policy: %s (%s)", root.path, result.error_message)
            continue
        path = result.sanitized_spec.source_path
        if is_within_boundary(path, work_dir):
            continue
        held = granted.get(path)
        if held is None or (root.writable and not held.writable):
            granted[path] = replace(root, path=path)
    return tuple(granted.values())


def build_workspace_sandbox_policy(
    work_dir: str,
    *,
    readonly: bool = False,
    allow_network: bool = True,
    granted_roots: Iterable[AccessRoot] = (),
) -> SandboxPolicy:
    """Build the OS sandbox policy for one workspace run, plus the directories granted beside it.

    The sandbox grants write access to the whole tree below ``work_dir``, so a root that equals or
    contains a dangerous system or user root (a home directory, a drive root) would hand those over
    too; it is refused with ``UnsafeWorkspaceError`` instead of silently dropped, so the caller
    never runs a command in a workspace it believes is protected. A workspace *inside* such a root
    is allowed: the grant reaches only its own subtree. A writable granted root becomes a writable tree
    and a read-only one a readable tree (``sandbox_grant_roots`` keeps out what the gate refuses). The git
    config and hooks of every repository found in a writable tree stay read-only. A read-only run writes
    nowhere, so every granted root is only readable in it.
    """
    grants = sandbox_grant_roots(work_dir, granted_roots)
    if readonly:
        return SandboxPolicy(
            writable_paths=(),
            readable_paths=tuple(grant.path for grant in grants),
            allow_network=allow_network,
        )
    result = validate_mount_spec(
        MountSpec(source_path=work_dir, mode=MountMode.RW, label="work_dir"),
        allow_dangerous_descendants=True,
    )
    if not result.is_valid or result.sanitized_spec is None:
        raise UnsafeWorkspaceError(f"Workspace root cannot be granted write access: {result.error_message}")
    writable = (result.sanitized_spec.source_path, *(grant.path for grant in grants if grant.writable))
    return SandboxPolicy(
        writable_paths=writable,
        readable_paths=tuple(grant.path for grant in grants if not grant.writable),
        read_only_subpaths=tuple(
            dict.fromkeys(path for tree in writable for path in discover_protected_subpaths(tree))
        ),
        allow_network=allow_network,
    )
