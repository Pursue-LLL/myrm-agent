"""The files a file tool opens, as the permission engine judges them: the zone verdict and the places a rule can name.

A file is one place however a call types it (``private/a.md``, ``./private/a.md``, ``/workspace/private/a.md``, a host
path, a path through a link). The zone verdict reads every file a call may open through the same typed-path reading
the executor uses; ``canonical_forms`` gives the two spellings a rule that names a place can match, so the engine's
rule lookup judges the file and not only the text.

[INPUT]
- judged_paths::judged_file_paths (POS: every file a file tool may open: the typed ones and the respelling of a read)
- types::PermissionAction, SecurityConfig (POS: the verdict vocabulary and the policy a call is judged by)
- core.security.path::opened_path (POS: Aggregation facade for the path security domain)
- checks::check_command_protected_write, check_path_policy (POS: Layers 2 and 2.5 of the permission engine's deterministic evaluation; imported on use)
- session_access::merge_path_policy_with_session_access (POS: Runtime mutable directory grants for the current agent run; imported on use)

[OUTPUT]
- PATH_CHECKED_PERMISSIONS: the permission types whose tool input names files
- ACTION_SEVERITY: the order of the verdicts, DENY above ASK above ALLOW
- check_tool_path_policy(): strictest zone verdict over every file a file tool may open and the protected instruction files a shell command writes (engine and cron policy share it)
- canonical_forms(): where the files lie, as absolute paths with every link followed and as paths below the workspace

[POS]
Path half of the permission engine's deterministic evaluation (Layers 2.5 and 4): the zone verdict and the canonical
places of a call's files. Pure apart from the read-only resolution of the paths a call names.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from myrm_agent_harness.agent.security.judged_paths import judged_file_paths
from myrm_agent_harness.agent.security.types import PermissionAction, SecurityConfig
from myrm_agent_harness.core.security.path import opened_path

__all__ = ("ACTION_SEVERITY", "PATH_CHECKED_PERMISSIONS", "canonical_forms", "check_tool_path_policy")

PATH_CHECKED_PERMISSIONS: frozenset[str] = frozenset({"file_read", "file_write"})
ACTION_SEVERITY: dict[PermissionAction, int] = {
    PermissionAction.ALLOW: 0,
    PermissionAction.ASK: 1,
    PermissionAction.DENY: 2,
}


def check_tool_path_policy(
    permission: str,
    tool_input: dict[str, object],
    config: SecurityConfig,
    workspace_root: str | None,
) -> tuple[PermissionAction, str] | None:
    """Strictest verdict over what a call touches that needs a person; ``None`` if it touches nothing of the kind.

    A file tool is judged by the zones (session grants included) of every file it may open (``judged_file_paths``),
    a shell tool by whether its command writes a protected instruction file.
    """
    from myrm_agent_harness.agent.security.checks import check_command_protected_write, check_path_policy

    paths = judged_file_paths(permission, tool_input, workspace_root) if permission in PATH_CHECKED_PERMISSIONS else []
    if not paths:
        return check_command_protected_write(permission, tool_input)

    from myrm_agent_harness.agent.security.session_access import merge_path_policy_with_session_access

    policy = merge_path_policy_with_session_access(config.path_policy)
    verdicts = [
        check_path_policy(path, policy, workspace_root, require_write=permission == "file_write") for path in paths
    ]
    return max(verdicts, key=lambda verdict: ACTION_SEVERITY[verdict[0]])


def canonical_forms(paths: Sequence[str], workspace_root: str | None) -> tuple[str, ...]:
    """The places the files lie, spelled the two ways a rule can name a place; the typed paths are not repeated.

    A rule such as ``private/*`` or ``/home/me/ws/private/*`` matches the text it is given, and a call can type one
    file as ``docs/../private/a.md``, ``/workspace/private/a.md`` or through a link. Each file is therefore also given
    as its absolute path with every link followed (``opened_path``: the file the tools open) and, when it lies in the
    workspace, as that path below the workspace. ``*`` stands for a call that names no file, and a text no file can be
    named by has no place.
    """
    root = os.path.realpath(workspace_root) if workspace_root else None
    forms: dict[str, None] = {}
    for path in paths:
        opened = opened_path(path, workspace_root) if path != "*" else None
        if opened is None:
            continue
        forms[opened] = None
        if root and (opened == root or opened.startswith(root + os.sep)):
            forms[os.path.relpath(opened, root)] = None
    return tuple(form for form in forms if form not in paths)
