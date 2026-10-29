"""Runtime ContextVars for workspace trust during agent execution.

[INPUT]
- contextvars::ContextVar (POS: Python 异步上下文变量标准库)
- agent.security.workspace_trust.types::WorkspaceTrustLevel
  (POS: 工作区信任级别类型)
- agent.security.workspace_trust.gate::blocks_workspace_side_channels
  (POS: pure predicate: which trust levels keep repo-local side channels closed)

[OUTPUT]
- set/get_workspace_trust_level, set/get_workspace_root, and set/get_repo_command_prefixes accessors
- workspace_side_channels_blocked: whether the run's trust level keeps repo-local side channels closed
- clear_workspace_trust_context: resets all vars at run end

[POS]
Run-scoped state holder of the workspace_trust gate. ContextVars keep the decision
isolated per async task, so concurrent runs on different workspaces never observe each
other's trust level. Values are populated by runtime.py from a server-injected lookup.
"""

from __future__ import annotations

from contextvars import ContextVar

from . import gate
from .types import WorkspaceTrustLevel

_workspace_trust_level_var: ContextVar[WorkspaceTrustLevel | None] = ContextVar(
    "workspace_trust_level",
    default=None,
)
_workspace_root_var: ContextVar[str | None] = ContextVar(
    "workspace_trust_root",
    default=None,
)
_repo_command_prefixes_var: ContextVar[tuple[str, ...]] = ContextVar(
    "repo_command_prefixes",
    default=(),
)


def set_workspace_trust_level(level: WorkspaceTrustLevel | None) -> None:
    """Bind the active workspace trust level for the current async context."""
    _workspace_trust_level_var.set(level)


def get_workspace_trust_level() -> WorkspaceTrustLevel | None:
    """Return the active workspace trust level, if any."""
    return _workspace_trust_level_var.get()


def workspace_side_channels_blocked() -> bool:
    """Whether the active run's trust level keeps repo-local side channels closed; a run with no level counts as restricted."""
    return gate.blocks_workspace_side_channels(get_workspace_trust_level())


def set_workspace_root(workspace_root: str | None) -> None:
    """Bind the active workspace root path for the current async context."""
    _workspace_root_var.set(workspace_root)


def get_workspace_root() -> str | None:
    """Return the active workspace root path bound for the current async context."""
    return _workspace_root_var.get()


def set_repo_command_prefixes(prefixes: tuple[str, ...]) -> None:
    """Bind repo-declared command prefixes effective only for trusted workspaces."""
    _repo_command_prefixes_var.set(prefixes)


def get_repo_command_prefixes() -> tuple[str, ...]:
    """Return repo command prefixes bound for the current async context."""
    return _repo_command_prefixes_var.get()


def clear_workspace_trust_context() -> None:
    """Reset trust-related ContextVars at run end."""
    _workspace_trust_level_var.set(None)
    _workspace_root_var.set(None)
    _repo_command_prefixes_var.set(())
