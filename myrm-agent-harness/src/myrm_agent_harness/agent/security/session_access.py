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


def _realpath(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def grant_session_access_root(
    root: AccessRoot,
    *,
    policy: PathPolicy | None = None,
    workspace_root: str | None = None,
) -> tuple[AccessRoot, ...]:
    """Add a HITL-granted root, or raise a held read-only one to writable (dedupe by normalized path)."""
    current = get_session_access_roots()
    normalized = resolve_grant_directory_path(root.path, workspace_root)
    if not normalized:
        return current

    held_index = next((i for i, held in enumerate(current) if _realpath(held.path) == normalized), None)
    if held_index is None and len(current) >= _MAX_GRANTS_PER_SESSION:
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

    if held_index is None:
        updated = (*current, replace(root, path=normalized))
    elif root.writable and not current[held_index].writable:
        updated = (*current[:held_index], replace(current[held_index], writable=True), *current[held_index + 1 :])
    else:
        return current
    set_session_access_roots(updated)
    return updated


def plan_directory_grants(
    tool_input: dict[str, object],
    *,
    policy: PathPolicy,
    workspace_root: str | None,
    writable: bool,
) -> list[AccessRoot]:
    """The directories "also grant folder access" would add or upgrade for this call, each once.

    One per directory of a file the call names outside the allowed zones; a write into a held read-only
    folder offers its upgrade to writable. Files inside the workspace or an allowed root need no grant, so
    a batched call does not spend the per-session grant limit on them; a directory the grant would be
    refused (forbidden zone, limit reached) is not offered either, so the card never promises a folder the
    grant then drops. ``policy`` is the effective one for the turn.
    """
    current = get_session_access_roots()
    held = {_realpath(root.path) for root in current}
    room = _MAX_GRANTS_PER_SESSION - len(current)
    planned: dict[str, AccessRoot] = {}
    new_roots = 0
    for raw_path in host_file_paths(tool_input):
        action, _ = check_path_policy(raw_path, policy, workspace_root, require_write=writable)
        if action != PermissionAction.ASK:
            continue
        grant_path = resolve_grant_directory_path(raw_path, workspace_root)
        if not grant_path or grant_path in planned:
            continue
        is_new = grant_path not in held
        if is_new and new_roots >= room:
            continue
        if _grant_path_blocked_by_policy(grant_path, policy, workspace_root, require_write=writable):
            continue
        planned[grant_path] = AccessRoot(path=grant_path, writable=writable, source="path_ask_grant")
        new_roots += is_new
    return list(planned.values())


def grant_directories_for_call(
    tool_input: dict[str, object],
    *,
    policy: PathPolicy,
    workspace_root: str | None,
    writable: bool,
) -> list[str]:
    """Grant the directories ``plan_directory_grants`` names; return the ones actually added or upgraded."""
    granted: list[str] = []
    for root in plan_directory_grants(tool_input, policy=policy, workspace_root=workspace_root, writable=writable):
        roots_before = get_session_access_roots()
        if grant_session_access_root(root, policy=policy, workspace_root=workspace_root) != roots_before:
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
    updated = tuple(root for root in current if _realpath(root.path) != target)
    if len(updated) == len(current):
        return current
    set_session_access_roots(updated)
    return updated


def merge_path_policy_with_session_access(policy: PathPolicy) -> PathPolicy:
    """Overlay session HITL grants onto the static PathPolicy for this turn."""
    session_roots = get_session_access_roots()
    if not session_roots:
        return policy
    by_path: dict[str, AccessRoot] = {_realpath(r.path): r for r in policy.access_roots}
    for root in session_roots:
        key = _realpath(root.path)
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
        ws_norm = _realpath(workspace_root) if workspace_root else ""
        root_norm = _realpath(root.path)
        if ws_norm and root_norm == ws_norm:
            continue
        access = "read-write" if root.writable else "read-only"
        label = f" ({root.label})" if root.label else ""
        lines.append(f"- {root.path} [{access}]{label}")
    lines.append("Relative paths resolve against the primary workspace.")
    return "\n".join(lines)
