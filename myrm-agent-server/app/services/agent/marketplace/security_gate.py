"""Tighten-only gate for ``security_overrides`` that arrive from outside the user's machine.

An agent override can *loosen* security when the user has no global policy
(the user-level ceiling only exists once a user config is present), so every
external source (marketplace install, control-plane force-push, any future
importer) must pass its overrides through this single gate first.

Rule: an imported override may only make the effective policy stricter than the
product baseline (``DEFAULT_RULESET`` + default path/network policy). Anything
that could relax it is dropped, anything unknown is dropped (default-deny).

[INPUT]
-- myrm_agent_harness.core.security.types::DEFAULT_RULESET / PermissionAction (POS: baseline rules)
-- myrm_agent_harness.agent.security.config::expand_capability_surface_permissions /
   normalize_delegate_permissions (POS: the same key expansion the parser applies)

[OUTPUT]
-- restrict_external_security_overrides: raw overrides → tightened overrides or None.

[POS]
Single choke point for externally supplied security overrides; pure function, no I/O.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from fnmatch import fnmatchcase

from myrm_agent_harness.agent.security.config import (
    expand_capability_surface_permissions,
    normalize_delegate_permissions,
)
from myrm_agent_harness.core.security.types import DEFAULT_RULESET, PermissionAction

logger = logging.getLogger(__name__)

# Both spellings are accepted by the harness parser; the gate preserves the spelling it received.
_PERMISSION_KEYS = ("permissions", "capabilityMatrix", "capability_matrix")
_INJECTION_POLICY_KEYS = ("injectionPolicy", "injection_policy")
_STRICT_INJECTION_POLICY = "fail_closed"

_BASELINE_DENIES: tuple[str, ...] = tuple(
    rule.permission for rule in DEFAULT_RULESET if rule.action is PermissionAction.DENY
)


def restrict_external_security_overrides(raw: object) -> dict[str, object] | None:
    """Return the part of ``raw`` that can only tighten the baseline, or None when nothing survives."""
    if not isinstance(raw, Mapping) or not raw:
        return None

    kept: dict[str, object] = {}
    for key in _PERMISSION_KEYS:
        permissions = _restrict_permissions(raw.get(key))
        if permissions:
            kept[key] = permissions

    # Capabilities are intersected with the user's set by the merger, so they can only restrict.
    capabilities = raw.get("capabilities")
    if isinstance(capabilities, list) and capabilities:
        kept["capabilities"] = list(capabilities)

    for key in ("networkBlocklist", "commandDenylist"):
        entries = _clean_strings(raw.get(key))
        if entries:
            kept[key] = entries

    if raw.get("domainHitlEnabled") is True:
        kept["domainHitlEnabled"] = True

    for key in _INJECTION_POLICY_KEYS:
        if raw.get(key) == _STRICT_INJECTION_POLICY:
            kept[key] = _STRICT_INJECTION_POLICY

    dropped = sorted(str(key) for key in raw if key not in kept)
    if dropped:
        logger.info("External security overrides tightened; dropped keys: %s", dropped)
    return kept or None


def _restrict_permissions(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        return {}
    restricted: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        governed = _governed_permissions(key)
        if isinstance(value, str):
            if _is_tightening(governed, value):
                restricted[key] = value
        elif isinstance(value, Mapping):
            patterns = {
                pattern: action
                for pattern, action in value.items()
                if isinstance(pattern, str) and isinstance(action, str) and _is_tightening(governed, action)
            }
            if patterns:
                restricted[key] = patterns
    return restricted


def _governed_permissions(key: str) -> frozenset[str]:
    """Every permission name a config key ends up governing (surface and legacy-delegate fan-out included)."""
    expanded = expand_capability_surface_permissions(normalize_delegate_permissions({key: "ask"}))
    return frozenset(expanded)


def _is_tightening(governed: frozenset[str], action: str) -> bool:
    """``deny`` always tightens; ``ask`` tightens unless it would soften a baseline deny; the rest loosens."""
    if action == PermissionAction.DENY.value:
        return True
    if action == PermissionAction.ASK.value:
        return not any(_overlaps(permission, deny) for permission in governed for deny in _BASELINE_DENIES)
    return False


def _overlaps(permission: str, baseline_permission: str) -> bool:
    """Wildcard-aware overlap in both directions (``browser_*`` vs ``browser_evaluate``, ``*`` vs anything)."""
    return fnmatchcase(baseline_permission, permission) or fnmatchcase(permission, baseline_permission)


def _clean_strings(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [item.strip() for item in raw if isinstance(item, str) and item.strip()]
