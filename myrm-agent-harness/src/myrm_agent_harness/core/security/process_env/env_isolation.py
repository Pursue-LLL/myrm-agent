"""Child process environment variable isolation and security sanitization.

SSOT for preventing privileged host secrets (Noise auth tokens, Vault master keys,
database passwords, API credentials) from leaking into child processes (Bash sessions,
hooks, CUA drivers, subcommands).

[INPUT]
- base_env: Optional source environment dict (defaults to os.environ).
- extra_env: Explicit caller overrides (e.g. context.env or specific task vars).
- inherit_policy: EnvInheritPolicy (CORE, ALL, NONE).
- env_name_tables::DEFAULT_CHILD_SAFE_ENV_KEYS, FORBIDDEN_EXACT_KEYS, SENSITIVE_WILDCARDS, DANGEROUS_PREFIXES, PTC_ORCHESTRATION_ENV_KEYS (POS: The name tables behind env_isolation)

[OUTPUT]
- build_isolated_child_env: Pure constructor returning sanitized child environment.
- sanitize_env: Sanitizes a given environment dict according to policy.
- EnvInheritPolicy: Enum (CORE, ALL, NONE).

[POS]
Core security SSOT for the environment a started process gets; depends on no upper layer.
Referenced by:
- toolkits/code_execution/session/local_session.py, executors/local/* (shell sessions, one-shot commands)
- agent/hooks/executor.py (shell command hooks), core/security/safe_exec.py, toolkits/acp/runtime/_base.py
- toolkits/computer_use/backends/cua_driver/backend.py (CUA stdio driver)
- toolkits/browser/pool/browser_launch_env.py (browser launch environment)
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum

from .env_name_tables import (
    DANGEROUS_PREFIXES,
    DEFAULT_CHILD_SAFE_ENV_KEYS,
    FORBIDDEN_EXACT_KEYS,
    PTC_ORCHESTRATION_ENV_KEYS,
    SENSITIVE_WILDCARDS,
)

logger = logging.getLogger(__name__)


class EnvInheritPolicy(StrEnum):
    """Subprocess environment inheritance strategy.

    CORE: Inherit only proven-safe core development and system variables.
          Recommended default for child processes executing untrusted/model code.
    ALL:  Inherit all parent variables, but strictly strip all sensitive patterns.
    NONE: Pass an empty base, accepting only sanitized explicit extra_env.
    """

    CORE = "core"
    ALL = "all"
    NONE = "none"


def _matches_wildcard(key: str) -> bool:
    """Check if env var name contains any dangerous wildcard pattern.

    Safeguards developer Git author variables (GIT_AUTHOR_NAME, GIT_AUTHOR_EMAIL, etc.)
    from false-positive matches against authentication prefixes.
    """
    upper = key.upper()
    for wildcard in SENSITIVE_WILDCARDS:
        if wildcard in upper:
            if (
                "AUTHOR" in upper
                and "AUTHORIZATION" not in upper
                and not any(p in upper for p in ("TOKEN", "KEY", "SECRET", "PASSWORD", "PASS"))
            ):
                continue
            return True
    return False


def _is_ptc_orchestration_env(env: dict[str, str]) -> bool:
    """True when env carries Dynamic Workflow PTC RPC bridge markers."""
    return "_MYRM_PTC_SOCKET" in env or "_MYRM_PTC_PORT" in env


def _is_sensitive_key(key: str) -> bool:
    """Return True if key matches any known secret pattern."""
    upper = key.upper()
    if upper in FORBIDDEN_EXACT_KEYS or key in FORBIDDEN_EXACT_KEYS:
        return True
    if any(upper.startswith(prefix) for prefix in DANGEROUS_PREFIXES):
        return True
    return _matches_wildcard(key)


def is_non_inheritable_env_var(key: str) -> bool:
    """Return True if the environment variable name is forbidden from child process inheritance.

    Implements case-insensitive detection for privilege escalation vectors, sensitive
    sockets (SSH/GPG), tokens, and cloud launch context.
    """
    return _is_sensitive_key(key)


def sanitize_env(
    env: dict[str, str],
    inherit_policy: EnvInheritPolicy = EnvInheritPolicy.ALL,
) -> dict[str, str]:
    """Filter environment variables based on security policy.

    Args:
        env: Source environment variable mapping.
        inherit_policy: Inheritance policy (default: ALL).

    Returns:
        A new dict containing only allowed, sanitized variables.
    """
    if inherit_policy == EnvInheritPolicy.NONE:
        return {}

    filtered: dict[str, str] = {}
    blocked: list[str] = []

    is_core = inherit_policy == EnvInheritPolicy.CORE
    ptc_orchestration = _is_ptc_orchestration_env(env)

    for key, value in env.items():
        # Allow internal PTC RPC bridge keys
        if key in PTC_ORCHESTRATION_ENV_KEYS:
            filtered[key] = value
            continue

        upper = key.upper()
        # PYTHONPATH is strictly blocked unless verified as a PTC orchestration session
        if upper == "PYTHONPATH":
            if ptc_orchestration:
                filtered[key] = value
                continue
            blocked.append(key)
            continue

        # Core whitelist check
        if is_core and upper not in DEFAULT_CHILD_SAFE_ENV_KEYS and key not in DEFAULT_CHILD_SAFE_ENV_KEYS:
            blocked.append(key)
            continue

        # Sensitive check
        if _is_sensitive_key(key):
            blocked.append(key)
            continue

        filtered[key] = value

    if blocked:
        logger.debug(
            "Child process env filtered %d variables (%s): %s",
            len(blocked),
            inherit_policy,
            ", ".join(sorted(blocked)[:15]),
        )

    return filtered


def build_isolated_child_env(
    base_env: dict[str, str] | None = None,
    extra_env: dict[str, str] | None = None,
    inherit_policy: EnvInheritPolicy = EnvInheritPolicy.CORE,
) -> dict[str, str]:
    """Build an isolated, secure environment dictionary for child process spawning.

    1. Starts with sanitized base environment under the specified policy (default CORE).
    2. Overrides with explicitly provided extra_env (after stripping injection vectors).
    3. Strictly scrubs non-inheritable credentials post-override.

    Args:
        base_env: Base environment (defaults to os.environ if None).
        extra_env: Explicit overrides requested by caller or user context.
        inherit_policy: Inheritance strategy (CORE, ALL, NONE). Defaults to CORE.

    Returns:
        Sanitized environment dictionary safe for child execution.
    """
    raw_base = dict(os.environ) if base_env is None else dict(base_env)
    sanitized = sanitize_env(raw_base, inherit_policy=inherit_policy)

    if extra_env:
        # Extra environment variables explicitly requested by caller
        for k, v in extra_env.items():
            upper = k.upper()
            # Even in explicit overrides, strictly forbid dynamic linker injection
            if any(upper.startswith(p) for p in ("LD_", "DYLD_")):
                logger.warning("Blocked dynamic linker injection override in child env: %s", k)
                continue
            if upper in ("NODE_OPTIONS", "PYTHONSTARTUP"):
                logger.warning("Blocked interpreter startup injection override in child env: %s", k)
                continue
            # Auth tokens and launch context cannot be restored via overrides
            if _is_sensitive_key(k):
                logger.warning("Blocked non-inheritable override in child env: %s", k)
                continue
            sanitized[k] = str(v)

    # Post-override scrubbing guarantee: re-check all keys to prevent case-variant injection
    for k in list(sanitized.keys()):
        if _is_sensitive_key(k):
            logger.warning("Stripped non-inheritable variable from child env: %s", k)
            sanitized.pop(k, None)

    return sanitized
