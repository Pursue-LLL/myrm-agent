"""The file a typed path opens, read once for every gate and for the respelling probe.

The executor opens a typed path in one way: the container alias ``/workspace`` is the workspace, a bare ``~`` is the
user's home and nothing else is expanded, a relative spelling lies below the workspace, and every link in the path is
followed. The permission engine, the grant flow and the respelling probe must judge that file and no other, so they
share this reading instead of repeating it.

[INPUT]
- path.filesystem::expand_home (POS: Generic filesystem path safety — no product protection policy)

[OUTPUT]
- container_relative(path) -> str | None: the part of a path below the container alias ``/workspace`` (``.`` for the alias itself); None for any other path
- spelled_path(raw_path, workspace_root) -> str: the place the file tools look for a typed path, before any link is followed
- opened_path(raw_path, workspace_root) -> str | None: the file that place resolves to, every link followed; None for a text no file can be named by

[POS]
The one definition of which file a tool opens for the text it was given.
"""

from __future__ import annotations

import os

from myrm_agent_harness.core.security.path.filesystem import expand_home

__all__ = ("container_relative", "opened_path", "spelled_path")

# The sandbox shows the agent its workspace under this name.
_CONTAINER_ROOT = "/workspace"


def container_relative(path: str) -> str | None:
    """The part of *path* below the container alias ``/workspace`` (``.`` for the alias itself), or None.

    Whole path segments match, so ``/workspace2/x`` is another directory and no alias.
    """
    if path == _CONTAINER_ROOT:
        return "."
    if path.startswith(f"{_CONTAINER_ROOT}/"):
        return path[len(_CONTAINER_ROOT) + 1 :].lstrip("/") or "."
    return None


def spelled_path(raw_path: str, workspace_root: str | None) -> str:
    """The place the file tools look for *raw_path*, with no link followed.

    With a workspace known, ``/workspace/x`` is ``<workspace>/x``. A bare ``~`` is the user's home; ``$HOME`` and
    ``~name`` are file names, because the tools do not expand them. A relative spelling lies below the workspace when
    one is known.
    """
    spelled = expand_home((container_relative(raw_path) if workspace_root else None) or raw_path)
    if workspace_root and not os.path.isabs(spelled):
        return os.path.join(workspace_root, spelled)
    return spelled


def opened_path(raw_path: str, workspace_root: str | None) -> str | None:
    """The file the tools open for *raw_path*, with every link in it resolved.

    A link named like a variable (``$HOME -> .env``) is followed, not expanded away before the resolution that would
    have shown it. ``None`` when no file can be named by the text (a NUL byte, a character no file name encodes): the
    tools cannot open it, so a gate refuses it instead of raising.
    """
    try:
        return os.path.realpath(spelled_path(raw_path, workspace_root))
    except ValueError:
        return None
