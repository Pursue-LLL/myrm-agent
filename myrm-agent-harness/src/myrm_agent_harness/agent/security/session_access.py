"""Session-scoped directory access grants (path-ASK grant).

[INPUT]
- core.security.types::AccessRoot, PathPolicy
- core.context_vars::session_access_roots_var (POS: the grants, shared with the sandbox executor)

[OUTPUT]
- get_session_access_roots / set_session_access_roots / grant_session_access_root
- plan_directory_grants / grant_directories_for_call / PATH_WRITE_PERMISSION_TYPES
- revoke_session_access_root
- resolve_grant_directory_path
- merge_path_policy_with_session_access
- render_session_access_context

[POS]
Runtime mutable directory grants for the current agent run. Persisted by server on chat;
loaded into ContextVar at turn start.
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace

from myrm_agent_harness.agent.security.checks import check_path_policy
from myrm_agent_harness.agent.security.types import (
    AccessRoot,
    PathPolicy,
    PermissionAction,
)
from myrm_agent_harness.core.context_vars import session_access_roots_var
from myrm_agent_harness.core.security.tool_registry import host_file_paths

logger = logging.getLogger(__name__)

_MAX_GRANTS_PER_SESSION = 5

# Permission types whose directory grant is read-write; every other file tool grants read-only.
PATH_WRITE_PERMISSION_TYPES: frozenset[str] = frozenset({"file_write", "file_edit", "file_delete"})


def get_session_access_roots() -> tuple[AccessRoot, ...]:
    return session_access_roots_var.get()


def set_session_access_roots(roots: tuple[AccessRoot, ...]) -> None:
    session_access_roots_var.set(roots)


def resolve_grant_directory_path(
    raw_path: str,
    workspace_root: str | None,
) -> str:
    """Resolve a grant target to an absolute directory (workspace-relative when applicable)."""
    trimmed = raw_path.strip()
    if not trimmed:
        return ""
    if workspace_root and not os.path.isabs(os.path.expanduser(trimmed)):
        candidate = os.path.join(workspace_root, trimmed)
    else:
        candidate = trimmed
    expanded = os.path.realpath(os.path.expanduser(candidate))
    if os.path.isdir(expanded):
        return expanded
    return os.path.dirname(expanded)


def _grant_path_blocked_by_policy(
    grant_path: str,
    policy: PathPolicy,
    workspace_root: str | None,
    *,
    require_write: bool,
) -> str | None:
    action, reason = check_path_policy(
        grant_path,
        policy,
        workspace_root,
        require_write=require_write,
    )
    if action == PermissionAction.DENY:
        return reason
    return None


def grant_session_access_root(
    root: AccessRoot,
    *,
    policy: PathPolicy | None = None,
    workspace_root: str | None = None,
) -> tuple[AccessRoot, ...]:
    """Append a HITL-granted root (dedupe by normalized path). Returns updated tuple."""
    current = get_session_access_roots()
    if len(current) >= _MAX_GRANTS_PER_SESSION:
        return current

    normalized = resolve_grant_directory_path(root.path, workspace_root)
    if not normalized:
        return current

    if policy is not None:
        block_reason = _grant_path_blocked_by_policy(
            normalized,
            policy,
            workspace_root,
            require_write=root.writable,
        )
        if block_reason:
            logger.warning(
                "Directory grant rejected by path policy: %s (%s)",
                normalized,
                block_reason,
            )
            return current

    for existing in current:
        if os.path.realpath(os.path.expanduser(existing.path)) == normalized:
            return current
    updated = (*current, replace(root, path=normalized))
    set_session_access_roots(updated)
    return updated


def plan_directory_grants(
    tool_input: dict[str, object],
    *,
    policy: PathPolicy,
    workspace_root: str | None,
    writable: bool,
) -> list[AccessRoot]:
    """The directories "also grant folder access" would add for this call, each once.

    One per directory of a file the call names outside the allowed zones. Files inside the workspace or an
    allowed root need no grant, so a batched call does not spend the per-session grant limit on them; a
    directory the grant would be refused (forbidden zone, limit reached) is not offered either, so the
    card never promises a folder the grant then drops. ``policy`` is the effective one for the turn.
    """
    room = _MAX_GRANTS_PER_SESSION - len(get_session_access_roots())
    planned: dict[str, AccessRoot] = {}
    for raw_path in host_file_paths(tool_input):
        if len(planned) >= room:
            break
        action, _ = check_path_policy(raw_path, policy, workspace_root, require_write=writable)
        if action != PermissionAction.ASK:
            continue
        grant_path = resolve_grant_directory_path(raw_path, workspace_root)
        if not grant_path or grant_path in planned:
            continue
        if _grant_path_blocked_by_policy(grant_path, policy, workspace_root, require_write=writable):
            continue
        planned[grant_path] = AccessRoot(path=grant_path, writable=writable, source="path_ask_grant")
    return list(planned.values())


def grant_directories_for_call(
    tool_input: dict[str, object],
    *,
    policy: PathPolicy,
    workspace_root: str | None,
    writable: bool,
) -> list[str]:
    """Grant the directories ``plan_directory_grants`` names; return the ones actually added."""
    granted: list[str] = []
    for root in plan_directory_grants(tool_input, policy=policy, workspace_root=workspace_root, writable=writable):
        roots_before = get_session_access_roots()
        grant_session_access_root(root, policy=policy, workspace_root=workspace_root)
        if len(get_session_access_roots()) > len(roots_before):
            granted.append(root.path)
    return granted


def revoke_session_access_root(
    raw_path: str,
    *,
    workspace_root: str | None = None,
) -> tuple[AccessRoot, ...]:
    """Remove a HITL-granted root by normalized path. Returns updated tuple."""
    normalized = resolve_grant_directory_path(raw_path, workspace_root)
    if not normalized:
        return get_session_access_roots()

    target = os.path.realpath(normalized)
    current = get_session_access_roots()
    updated = tuple(root for root in current if os.path.realpath(os.path.expanduser(root.path)) != target)
    if len(updated) == len(current):
        return current
    set_session_access_roots(updated)
    return updated


def merge_path_policy_with_session_access(policy: PathPolicy) -> PathPolicy:
    """Overlay session HITL grants onto the static PathPolicy for this turn."""
    session_roots = get_session_access_roots()
    if not session_roots:
        return policy
    by_path: dict[str, AccessRoot] = {os.path.realpath(os.path.expanduser(r.path)): r for r in policy.access_roots}
    for root in session_roots:
        key = os.path.realpath(os.path.expanduser(root.path))
        by_path[key] = root
    return replace(policy, access_roots=tuple(by_path.values()))


def render_session_access_context(
    policy: PathPolicy,
    workspace_root: str | None,
) -> str:
    """Plain-text block listing directories available this turn (for middleware injection)."""
    effective = merge_path_policy_with_session_access(policy)
    if not effective.access_roots and not workspace_root:
        return ""
    lines = ["Available directories (file tools may use paths within these roots):"]
    if workspace_root:
        lines.append(f"- {workspace_root} [read-write] — primary workspace")
    for root in effective.access_roots:
        ws_norm = os.path.realpath(os.path.expanduser(workspace_root)) if workspace_root else ""
        root_norm = os.path.realpath(os.path.expanduser(root.path))
        if ws_norm and root_norm == ws_norm:
            continue
        access = "read-write" if root.writable else "read-only"
        label = f" ({root.label})" if root.label else ""
        lines.append(f"- {root.path} [{access}]{label}")
    lines.append("Relative paths resolve against the primary workspace.")
    return "\n".join(lines)
