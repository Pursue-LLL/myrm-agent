"""Execution-layer enforcement guard for Object-Capability access.

[INPUT]
- .types::CapabilityAction, CapabilityHandle, CapabilityDeniedError, ResourceScope
- .context::get_current_capability
- .token::verify_capability_signature
- .attenuation::_is_path_subscope (POS: path boundary test, symlinked aliases and resolved paths are one boundary)

[OUTPUT]
- check_capability_access: Non-raising boolean access probe
- enforce_capability_access: Fail-closed assertion raising CapabilityDeniedError

[POS]
Physical gatekeeper invoked by the local file and shell executors.
Ensures operations fail-closed when capability handles are expired, unsigned, or out of scope.
A handle's validity is stateless: its signature and its expiry, nothing held per spawn.
"""

from __future__ import annotations

import fnmatch

from myrm_agent_harness.core.security.ocap.attenuation import _is_path_subscope
from myrm_agent_harness.core.security.ocap.context import get_current_capability
from myrm_agent_harness.core.security.ocap.token import verify_capability_signature
from myrm_agent_harness.core.security.ocap.types import (
    CapabilityAction,
    CapabilityDeniedError,
    CapabilityHandle,
    ResourceScope,
)


def _is_usable(handle: CapabilityHandle) -> bool:
    return not handle.is_expired() and verify_capability_signature(handle)


def _is_in_scope(scope: ResourceScope, target: str) -> bool:
    """A scope without path patterns constrains no path."""
    return not scope.paths or any(_is_path_subscope(target, pattern) for pattern in scope.paths)


def _is_revoked(handle: CapabilityHandle, registry: object | None) -> bool:
    """Whether ``handle`` has been revoked in the registry that tracks it.

    Only the revocation table is consulted, never ``is_valid``: that call also reports True for
    a handle that was never registered, so using it here would treat any forged handle as
    legitimate. With no registry in hand the revocation state is unknown, and the caller's explicit
    registry is the only way to learn it.
    """
    if registry is None:
        from myrm_agent_harness.core.security.ocap.registry import get_default_capability_registry

        registry = get_default_capability_registry()
    checker = getattr(registry, "is_revoked", None)
    if checker is None:
        return False
    return bool(checker(handle.handle_id)) or bool(
        handle.parent_handle_id and checker(handle.parent_handle_id)
    )


def _target_allowed(scope: ResourceScope, action: CapabilityAction, target: str) -> bool:
    """Whether ``target`` is inside ``scope`` for the kind of resource ``action`` touches.

    EGRESS targets are domains and MCP targets are tool names, so matching them against the
    path patterns would either deny everything or allow everything. Path actions keep the
    lexical+realpath boundary test.
    """
    if action is CapabilityAction.EGRESS:
        return not scope.domains or any(fnmatch.fnmatchcase(target, d) for d in scope.domains)
    if action is CapabilityAction.MCP:
        return not scope.mcp_tools or any(fnmatch.fnmatchcase(target, m) for m in scope.mcp_tools)
    return not scope.paths or any(_is_path_subscope(target, pattern) for pattern in scope.paths)


def _denied_reason(scope: ResourceScope, action: CapabilityAction, target: str) -> str:
    """The sentence a denial carries, named after the boundary that rejected it."""
    if action is CapabilityAction.EGRESS:
        return f"Egress domain '{target}' is not in capability whitelist {list(scope.domains)}"
    if action is CapabilityAction.MCP:
        return f"MCP tool '{target}' is not in capability whitelist {list(scope.mcp_tools)}"
    return f"Path '{target}' is outside granted capability boundaries: {list(scope.paths)}"


def check_capability_access(
    action: CapabilityAction,
    target: str | None = None,
    handle: CapabilityHandle | None = None,
    registry: object | None = None,
) -> bool:
    """Evaluate whether the given action on target is permitted by the active capability.

    Args:
        action: Requested capability action
        target: File path or working directory the action applies to
        handle: Explicit capability handle (falls back to active context)

    Returns:
        True if permitted; False if expired, unsigned, or out of scope.
    """
    active_handle = handle if handle is not None else get_current_capability()
    if active_handle is None:
        # No capability constraint active on current execution thread
        return True

    if _is_revoked(active_handle, registry):
        return False

    if not _is_usable(active_handle) or action not in active_handle.actions:
        return False

    return target is None or _target_allowed(active_handle.scope, action, target)


def enforce_capability_access(
    action: CapabilityAction,
    target: str | None = None,
    handle: CapabilityHandle | None = None,
    registry: object | None = None,
) -> None:
    """Enforce capability check, raising CapabilityDeniedError if unauthorized."""
    active_handle = handle if handle is not None else get_current_capability()
    if active_handle is None:
        return

    if _is_revoked(active_handle, registry):
        raise CapabilityDeniedError(
            f"Capability handle '{active_handle.handle_id}' is invalid, expired, or revoked."
        )

    if not _is_usable(active_handle):
        raise CapabilityDeniedError(f"Capability handle '{active_handle.handle_id}' is invalid or expired.")

    if action not in active_handle.actions:
        raise CapabilityDeniedError(
            f"Action '{action.value}' denied by capability '{active_handle.handle_id}'. "
            f"Allowed actions: {[a.value for a in active_handle.actions]}"
        )

    if target is not None and not _target_allowed(active_handle.scope, action, target):
        raise CapabilityDeniedError(_denied_reason(active_handle.scope, action, target))
